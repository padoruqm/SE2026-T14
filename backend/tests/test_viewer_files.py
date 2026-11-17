from __future__ import annotations

import tempfile
import time
import unittest
from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.processing import ProcessingContext, ProcessingResult
from las_fixtures import build_las

OCTREE = bytes(range(256)) * 4
SECRET = b"top secret"


class ResultProcessor:
    key = "result"
    input_schema: Mapping[str, object] = {"type": "object"}

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        out = context.output_directory
        out.mkdir()
        (out / "nested").mkdir()
        metadata = out / "metadata.json"
        metadata.write_text('{"version": "2.0"}', encoding="utf-8")
        (out / "octree.bin").write_bytes(OCTREE)
        (out / "nested" / "hierarchy.bin").write_bytes(b"hierarchy")
        return ProcessingResult(out, metadata)


class ViewerFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        settings = Settings(storage_root=self.root, max_upload_bytes=1024 * 1024)
        self.client = TestClient(create_app(settings, ResultProcessor()))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        (self.root / "secret.txt").write_bytes(SECRET)

    def _converted_point_cloud(self) -> str:
        upload = self.client.post("/api/upload", files={"file": ("a.las", build_las())})
        point_cloud_id = upload.json()["id"]
        self.client.post(f"/api/pointcloud/{point_cloud_id}/convert")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = self.client.get(f"/api/pointcloud/{point_cloud_id}").json()["status"]
            if status == "ready":
                return point_cloud_id
            time.sleep(0.01)
        self.fail("conversion did not finish")

    def _url(self, point_cloud_id: str, path: str) -> str:
        return f"/api/pointcloud/{point_cloud_id}/viewer/{path}"

    def test_serves_the_metadata_file_the_detail_endpoint_points_to(self) -> None:
        point_cloud_id = self._converted_point_cloud()
        detail = self.client.get(f"/api/pointcloud/{point_cloud_id}").json()

        response = self.client.get(detail["viewerUrl"])

        self.assertEqual(200, response.status_code)
        self.assertEqual({"version": "2.0"}, response.json())
        self.assertTrue(response.headers["content-type"].startswith("application/json"))

    def test_serves_binary_and_nested_files(self) -> None:
        point_cloud_id = self._converted_point_cloud()

        octree = self.client.get(self._url(point_cloud_id, "octree.bin"))
        nested = self.client.get(self._url(point_cloud_id, "nested/hierarchy.bin"))

        self.assertEqual(OCTREE, octree.content)
        self.assertEqual(b"hierarchy", nested.content)

    def test_supports_range_requests_for_the_octree(self) -> None:
        point_cloud_id = self._converted_point_cloud()

        response = self.client.get(
            self._url(point_cloud_id, "octree.bin"), headers={"Range": "bytes=10-19"}
        )

        self.assertEqual(206, response.status_code)
        self.assertEqual(OCTREE[10:20], response.content)

    def test_unknown_point_cloud_is_not_found(self) -> None:
        response = self.client.get(self._url("pc_missing", "metadata.json"))

        self.assertEqual(404, response.status_code)
        self.assertEqual("NOT_FOUND", response.json()["error"]["code"])

    def test_point_cloud_without_a_result_is_not_found(self) -> None:
        upload = self.client.post("/api/upload", files={"file": ("a.las", build_las())})

        response = self.client.get(self._url(upload.json()["id"], "metadata.json"))

        self.assertEqual(404, response.status_code)

    def test_missing_file_and_directories_are_not_found(self) -> None:
        point_cloud_id = self._converted_point_cloud()

        for path in ("nope.bin", "nested", "nested/", "nested/missing.bin", ""):
            with self.subTest(path=path):
                response = self.client.get(self._url(point_cloud_id, path))
                self.assertEqual(404, response.status_code)

    def test_cannot_leave_the_result_directory(self) -> None:
        point_cloud_id = self._converted_point_cloud()
        uploaded = next((self.root / "uploads").iterdir())

        for path in (
            "../../../secret.txt",
            "..%2F..%2F..%2Fsecret.txt",
            "%2e%2e/%2e%2e/%2e%2e/secret.txt",
            "nested/../../../../secret.txt",
            "..\\\\..\\\\..\\\\secret.txt",
            f"../../../uploads/{uploaded.name}",
            "/etc/passwd",
            "octree.bin%00.txt",
        ):
            with self.subTest(path=path):
                response = self.client.get(self._url(point_cloud_id, path))
                self.assertEqual(404, response.status_code)
                self.assertNotIn(SECRET, response.content)

    def test_cannot_reach_another_datasets_result(self) -> None:
        first = self._converted_point_cloud()
        second = self._converted_point_cloud()

        for path in (f"..%2F{second}%2Fmetadata.json", f"%2e%2e/{second}/metadata.json"):
            with self.subTest(path=path):
                response = self.client.get(self._url(first, path))
                self.assertEqual(404, response.status_code)
                self.assertNotIn(b"version", response.content)

    def test_does_not_follow_a_symlink_out_of_the_result(self) -> None:
        point_cloud_id = self._converted_point_cloud()
        result = self.root / "converted" / point_cloud_id
        (result / "leak.txt").symlink_to(self.root / "secret.txt")
        (result / "linked").symlink_to(self.root)

        for path in ("leak.txt", "linked/secret.txt"):
            with self.subTest(path=path):
                response = self.client.get(self._url(point_cloud_id, path))
                self.assertEqual(404, response.status_code)
                self.assertNotIn(SECRET, response.content)

    def test_not_found_responses_do_not_reveal_filesystem_paths(self) -> None:
        point_cloud_id = self._converted_point_cloud()

        response = self.client.get(self._url(point_cloud_id, "nope.bin"))

        self.assertNotIn(str(self.root), response.text)


if __name__ == "__main__":
    unittest.main()
