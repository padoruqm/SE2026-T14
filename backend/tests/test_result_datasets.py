from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import GoneError, NotFoundError
from app.main import create_app
from app.services.datasets import DatasetService
from app.services.las_metadata import LasBounds, LasMetadata
from las_fixtures import build_las

CROPPED = LasMetadata(
    point_count=10,
    bounds=LasBounds(1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
    crs="EPSG:32648",
)


class ResultDatasetTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        # Resolved so a symlinked temp directory does not look like a symlinked store.
        self.root = Path(temporary_directory.name).resolve()
        settings = Settings(storage_root=self.root, max_upload_bytes=1024 * 1024)
        self.client = TestClient(create_app(settings), raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.storage = self.client.app.state.storage
        self.service = DatasetService(self.storage, self.client.app.state.job_store)

    def _upload(self) -> str:
        response = self.client.post(
            "/api/upload", files={"file": ("survey.las", build_las())}
        )
        self.assertEqual(201, response.status_code)
        return response.json()["id"]

    def _converted_source(self) -> str:
        """An upload that has a converted result, as after a successful conversion."""
        source_id = self._upload()
        self._publish(source_id)
        return source_id

    def _publish(self, dataset_id: str) -> None:
        staging = self.storage.new_staging_dir(dataset_id)
        (staging / "metadata.json").write_text('{"version": "2.0"}', encoding="utf-8")
        self.storage.publish_converted(dataset_id, staging)

    def _result(self, source_id: str) -> str:
        staging = self.storage.new_staging_dir("crop")
        (staging / "metadata.json").write_text('{"version": "2.0"}', encoding="utf-8")
        return self.service.create_result(
            source_id, "survey-crop.las", CROPPED, staging
        ).id

    def _assert_error(self, response, status: int, code: str) -> None:
        self.assertEqual(status, response.status_code)
        self.assertEqual(code, response.json()["error"]["code"])

    def test_a_result_gets_its_own_id_and_points_back_to_its_source(self) -> None:
        source_id = self._converted_source()

        result_id = self._result(source_id)

        self.assertNotEqual(source_id, result_id)
        self.assertTrue(result_id.startswith("pc_"))
        detail = self.client.get(f"/api/pointcloud/{result_id}")
        self.assertEqual(200, detail.status_code)
        body = detail.json()
        self.assertEqual("ready", body["status"])
        self.assertEqual("survey-crop.las", body["filename"])
        self.assertEqual(source_id, body["sourceId"])
        self.assertEqual(f"/api/pointcloud/{result_id}/viewer/metadata.json", body["viewerUrl"])
        self.assertEqual(10, body["metadata"]["pointCount"])
        self.assertEqual(6.0, body["metadata"]["bounds"]["maxZ"])
        self.assertEqual("EPSG:32648", body["metadata"]["crs"])

    def test_a_source_has_no_source_id_and_is_left_untouched(self) -> None:
        source_id = self._converted_source()
        self._result(source_id)

        body = self.client.get(f"/api/pointcloud/{source_id}").json()

        self.assertIsNone(body["sourceId"])
        self.assertEqual("ready", body["status"])

    def test_the_result_files_are_served_under_the_result_id(self) -> None:
        result_id = self._result(self._converted_source())

        response = self.client.get(f"/api/pointcloud/{result_id}/viewer/metadata.json")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"version": "2.0"}, response.json())

    def test_an_unknown_id_is_404_for_detail_and_viewer_files(self) -> None:
        self._assert_error(self.client.get("/api/pointcloud/pc_unknown"), 404, "NOT_FOUND")
        self._assert_error(
            self.client.get("/api/pointcloud/pc_unknown/viewer/metadata.json"),
            404,
            "NOT_FOUND",
        )

    def test_a_result_whose_files_were_removed_is_410(self) -> None:
        result_id = self._result(self._converted_source())
        shutil.rmtree(self.root / "converted" / result_id)

        detail = self.client.get(f"/api/pointcloud/{result_id}")
        viewer = self.client.get(f"/api/pointcloud/{result_id}/viewer/metadata.json")

        self._assert_error(detail, 410, "GONE")
        self._assert_error(viewer, 410, "GONE")
        self.assertIn("no longer available", detail.json()["error"]["message"])

    def test_a_missing_file_inside_an_existing_result_is_still_404(self) -> None:
        result_id = self._result(self._converted_source())

        response = self.client.get(f"/api/pointcloud/{result_id}/viewer/missing.bin")

        self._assert_error(response, 404, "NOT_FOUND")

    def test_an_upload_that_is_not_converted_yet_is_not_gone(self) -> None:
        source_id = self._upload()

        detail = self.client.get(f"/api/pointcloud/{source_id}")
        viewer = self.client.get(f"/api/pointcloud/{source_id}/viewer/metadata.json")

        self.assertEqual("uploaded", detail.json()["status"])
        self._assert_error(viewer, 404, "NOT_FOUND")

    def test_an_upload_whose_file_was_removed_is_410(self) -> None:
        source_id = self._upload()
        self.storage.discard_upload(source_id)

        self._assert_error(self.client.get(f"/api/pointcloud/{source_id}"), 410, "GONE")

    def test_a_converted_upload_is_not_gone_without_its_original_file(self) -> None:
        source_id = self._converted_source()
        self.storage.discard_upload(source_id)

        self.assertEqual(200, self.client.get(f"/api/pointcloud/{source_id}").status_code)

    def test_a_result_needs_an_existing_source(self) -> None:
        staging = self.storage.new_staging_dir("crop")

        with self.assertRaises(NotFoundError):
            self.service.create_result("pc_unknown", "crop.las", CROPPED, staging)

        self.assertFalse(any((self.root / "converted").glob("pc_*")))

    def test_a_result_cannot_be_made_from_a_source_that_is_gone(self) -> None:
        source_id = self._upload()
        self.storage.discard_upload(source_id)
        staging = self.storage.new_staging_dir("crop")

        with self.assertRaises(GoneError):
            self.service.create_result(source_id, "crop.las", CROPPED, staging)

    def test_a_failed_record_write_leaves_no_converted_files_behind(self) -> None:
        source_id = self._converted_source()
        staging = self.storage.new_staging_dir("crop")

        with mock.patch.object(
            self.storage, "write_record", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                self.service.create_result(source_id, "crop.las", CROPPED, staging)

        self.assertEqual([source_id], [p.name for p in (self.root / "converted").glob("pc_*")])

    def _cropped_file(self, name: str = "cropped.laz") -> Path:
        work = self.root / "work"
        work.mkdir(exist_ok=True)
        path = work / name
        path.write_bytes(build_las())
        return path

    def test_a_result_keeps_its_point_cloud_file(self) -> None:
        source_id = self._converted_source()
        staging = self.storage.new_staging_dir("crop")
        (staging / "metadata.json").write_text('{"version": "2.0"}', encoding="utf-8")
        cropped = self._cropped_file()

        result = self.service.create_result(
            source_id, "survey-crop.laz", CROPPED, staging, source_file=cropped
        )

        stored = self.storage.find(result.id)
        self.assertEqual(f"{result.id}.laz", stored.name)
        self.assertFalse(cropped.exists())
        self.assertEqual("ready", self.service.get(result.id).status)

    def test_a_failed_record_write_leaves_neither_files_nor_point_cloud_behind(self) -> None:
        source_id = self._converted_source()
        staging = self.storage.new_staging_dir("crop")
        (staging / "metadata.json").write_text("{}", encoding="utf-8")
        before = sorted(p.name for p in (self.root / "uploads").iterdir())

        with mock.patch.object(self.storage, "write_record", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.service.create_result(
                    source_id,
                    "crop.laz",
                    CROPPED,
                    staging,
                    source_file=self._cropped_file(),
                )

        self.assertEqual(before, sorted(p.name for p in (self.root / "uploads").iterdir()))
        converted = [p.name for p in (self.root / "converted").iterdir()]
        self.assertEqual([source_id], [n for n in converted if not n.startswith(".")])

    def test_discard_converted_ignores_unknown_and_invalid_ids(self) -> None:
        self.storage.discard_converted("pc_unknown")
        self.storage.discard_converted("../metadata")


if __name__ == "__main__":
    unittest.main()
