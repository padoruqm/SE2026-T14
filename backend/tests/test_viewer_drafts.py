"""VT-055 public contract tests, derived from PLAN.md before implementation."""
from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from las_fixtures import build_las

DEFAULT = {"pointSize": 1.0, "colorMode": "rgb"}
NEWER = {"pointSize": 4.0, "colorMode": "elevation"}
OLDER = {"pointSize": 2.5, "colorMode": "intensity"}


class ViewerDraftApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.settings = Settings(storage_root=self.root, max_upload_bytes=1 << 20)
        uploads = self.root / "uploads"
        uploads.mkdir()
        for dataset in ("pc_alpha", "pc_beta"):
            (uploads / f"{dataset}.las").write_bytes(build_las())
        self.app = create_app(self.settings)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.path = "/api/pointcloud/pc_alpha/draft"

    def save(self, base=0, op="edit-1", state=None, path=None):
        return self.client.put(
            path or self.path,
            json={"expectedRevision": base, "operationId": op, "state": state or NEWER},
        )

    def assert_current(self, revision, state):
        response = self.client.get(self.path)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({"revision": revision, "state": state}, response.json())

    def test_T01_new_draft_has_contract_defaults(self):
        self.assert_current(0, DEFAULT)

    def test_T02_save_restores_exact_state_after_application_restart(self):
        saved = self.save()
        self.assertEqual(200, saved.status_code, saved.text)
        self.assertEqual({"revision": 1, "state": NEWER}, saved.json())
        with TestClient(create_app(self.settings)) as restarted:
            self.assertEqual(saved.json(), restarted.get(self.path).json())

    def test_T03_delayed_stale_save_cannot_replace_newer_data(self):
        self.assertEqual(200, self.save().status_code)
        stale = self.save(0, "delayed-old", OLDER)
        self.assertEqual(409, stale.status_code, stale.text)
        self.assert_current(1, NEWER)

    def test_T04_duplicate_operation_and_old_replay_do_not_advance_or_rollback(self):
        original = self.save()
        self.assertEqual(200, original.status_code, original.text)
        replay = self.save()
        self.assertEqual(original.json(), replay.json())
        self.assertEqual(200, self.save(1, "edit-2", OLDER).status_code)
        late_replay = self.save()
        self.assertEqual(200, late_replay.status_code)
        self.assertEqual(original.json(), late_replay.json())
        self.assert_current(2, OLDER)

    def test_T05_operation_id_cannot_be_reused_for_different_content(self):
        self.assertEqual(200, self.save().status_code)
        conflict = self.save(0, "edit-1", OLDER)
        self.assertEqual(409, conflict.status_code)
        self.assert_current(1, NEWER)

    def test_T06_point_size_boundaries_and_invalid_partitions(self):
        for size in (0.5, 5.5, 1.25, "NaN", "Infinity", True):
            with self.subTest(size=size):
                response = self.save(state={"pointSize": size, "colorMode": "rgb"})
                self.assertEqual(422, response.status_code, response.text)
        self.assert_current(0, DEFAULT)
        for base, size in enumerate((1, 5, 2.5)):
            response = self.save(base, f"valid-{base}", {"pointSize": size, "colorMode": "rgb"})
            self.assertEqual(200, response.status_code)
            self.assertEqual(size, response.json()["state"]["pointSize"])

    def test_T07_unknown_color_mode_is_rejected_without_write(self):
        self.assertEqual(422, self.save(state={"pointSize": 2, "colorMode": "rainbow"}).status_code)
        self.assert_current(0, DEFAULT)

    def test_T08_invalid_revision_key_and_extra_fields_are_rejected(self):
        for base in (-1, 0.5, True):
            with self.subTest(base=base):
                self.assertEqual(422, self.save(base=base).status_code)
        for key in ("", "bad/key", "x" * 65):
            with self.subTest(key=key):
                self.assertEqual(422, self.save(op=key).status_code)
        body = {"expectedRevision": 0, "operationId": "extra", "state": NEWER, "timestamp": 999}
        self.assertEqual(422, self.client.put(self.path, json=body).status_code)
        self.assert_current(0, DEFAULT)

    def test_T09_unknown_dataset_returns_404(self):
        unknown = "/api/pointcloud/pc_missing/draft"
        self.assertEqual(404, self.client.get(unknown).status_code)
        self.assertEqual(404, self.save(path=unknown).status_code)

    def test_T10_storage_failure_rolls_back_without_success_acknowledgement(self):
        self.assertEqual(200, self.save().status_code)
        # Adapter-level fault injection; the oracle is still the public GET result.
        with sqlite3.connect(self.root / "viewer-drafts.sqlite3") as connection:
            connection.execute("""CREATE TRIGGER fail_operation BEFORE INSERT ON draft_operations
                BEGIN SELECT RAISE(ABORT, 'injected operation write failure'); END""")
        failed = self.save(1, "edit-after-failure", OLDER)
        self.assertEqual(503, failed.status_code, failed.text)
        self.assertNotIn(str(self.root), failed.text)
        self.assert_current(1, NEWER)

    def concurrent(self, commands):
        barrier = threading.Barrier(len(commands), timeout=10)

        def send(command):
            with TestClient(self.app, raise_server_exceptions=False) as client:
                barrier.wait()
                return client.put(self.path, json=command)

        with ThreadPoolExecutor(max_workers=len(commands)) as executor:
            return list(executor.map(send, commands))

    def test_T11_two_writers_on_same_revision_have_exactly_one_winner(self):
        responses = self.concurrent([
            {"expectedRevision": 0, "operationId": "writer-a", "state": NEWER},
            {"expectedRevision": 0, "operationId": "writer-b", "state": OLDER},
        ])
        self.assertEqual([200, 409], sorted(r.status_code for r in responses))
        winner = next(r.json() for r in responses if r.status_code == 200)
        self.assert_current(1, winner["state"])

    def test_T12_simultaneous_retries_create_one_revision(self):
        command = {"expectedRevision": 0, "operationId": "same-operation", "state": NEWER}
        responses = self.concurrent([command, command])
        self.assertEqual([200, 200], [r.status_code for r in responses])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assert_current(1, NEWER)

    def test_T13_future_revision_on_new_draft_is_conflict(self):
        self.assertEqual(409, self.save(base=1).status_code)
        self.assert_current(0, DEFAULT)

    def test_T14_datasets_have_independent_revision_and_operation_spaces(self):
        self.assertEqual(200, self.save().status_code)
        other = self.save(state=OLDER, path="/api/pointcloud/pc_beta/draft")
        self.assertEqual(200, other.status_code)
        self.assertEqual(1, other.json()["revision"])
        self.assert_current(1, NEWER)


if __name__ == "__main__":
    unittest.main()
