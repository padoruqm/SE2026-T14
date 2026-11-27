from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.datasets import DatasetService
from app.services.las_metadata import LasBounds, LasMetadata
from test_crop_job import REGION, SOURCE, FakeConvert, FakeCrop


class CropValidationTest(unittest.TestCase):
    """What the crop endpoint refuses, and that a refusal creates no job or files."""

    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name).resolve()
        self.crop = FakeCrop()
        settings = Settings(storage_root=self.root, max_upload_bytes=1024 * 1024)
        self.client = TestClient(
            create_app(settings, FakeConvert(), crop_processor=self.crop),
            raise_server_exceptions=False,
        )
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        upload = self.client.post("/api/upload", files={"file": ("survey.las", SOURCE)})
        self.source_id = upload.json()["id"]

    def _post(self, body: object, point_cloud_id: str | None = None, raw=False):
        url = f"/api/pointcloud/{point_cloud_id or self.source_id}/crop"
        if raw:
            return self.client.post(
                url, content=body, headers={"Content-Type": "application/json"}
            )
        return self.client.post(url, json=body)

    def _assert_refused(self, response, status: int, code: str) -> dict:
        self.assertEqual(status, response.status_code, response.text)
        error = response.json()["error"]
        self.assertEqual(code, error["code"])
        self.assertEqual(error["requestId"], response.headers["X-Request-ID"])
        self.assertEqual([], self.crop.calls, "no crop may run after a refusal")
        self.assertEqual([], list(self.client.app.state.job_store._jobs.values()))
        return error

    def _region(self, **overrides: float) -> dict:
        return {"bounds": {**REGION, **overrides}}

    def test_an_empty_region_is_refused(self) -> None:
        for overrides in (
            {"maxX": REGION["minX"]},
            {"maxY": REGION["minY"]},
        ):
            with self.subTest(overrides=overrides):
                error = self._assert_refused(
                    self._post(self._region(**overrides)), 422, "VALIDATION_ERROR"
                )
                self.assertIn("no area", error["details"]["fields"][0]["reason"])
                self.assertEqual(
                    ["body", "bounds"], error["details"]["fields"][0]["location"]
                )

    def test_a_region_outside_the_point_cloud_is_refused(self) -> None:
        for overrides in (
            {"minX": 600000.0, "maxX": 600010.0},
            {"minY": 1000000.0, "maxY": 1000010.0},
            {"minZ": 50.0, "maxZ": 60.0},
            {"minX": 500100.0, "maxX": 500200.0},
        ):
            with self.subTest(overrides=overrides):
                error = self._assert_refused(
                    self._post(self._region(**overrides)), 422, "VALIDATION_ERROR"
                )
                self.assertIn(
                    "does not overlap", error["details"]["fields"][0]["reason"]
                )

    def test_reversed_bounds_are_refused(self) -> None:
        for axis in ("X", "Y", "Z"):
            with self.subTest(axis=axis):
                reversed_axis = {
                    f"min{axis}": REGION[f"max{axis}"],
                    f"max{axis}": REGION[f"min{axis}"],
                }
                error = self._assert_refused(
                    self._post(self._region(**reversed_axis)), 422, "VALIDATION_ERROR"
                )
                self.assertIn(f"min{axis}", error["details"]["fields"][0]["reason"])

    def test_values_that_are_not_finite_numbers_are_refused(self) -> None:
        for value in (
            "NaN",
            "Infinity",
            "-Infinity",
            "1e400",
            "true",
            '"500010"',
            "null",
        ):
            with self.subTest(value=value):
                body = json.dumps({"bounds": REGION}).replace(
                    json.dumps(REGION["minX"]), value, 1
                )
                self._assert_refused(
                    self._post(body, raw=True), 422, "VALIDATION_ERROR"
                )

    def test_incomplete_or_unexpected_fields_are_refused(self) -> None:
        missing = {k: v for k, v in REGION.items() if k != "maxZ"}
        for body in (
            {},
            {"bounds": missing},
            {"bounds": {**REGION, "maxW": 1.0}},
            {"bounds": REGION, "outputFormat": "ply"},
            {"bounds": REGION, "pipeline": [{"type": "filters.crop"}]},
            {"bounds": REGION, "outputFormat": "LAZ"},
        ):
            with self.subTest(body=body):
                self._assert_refused(self._post(body), 422, "VALIDATION_ERROR")

    def test_a_body_that_is_not_json_is_refused(self) -> None:
        self._assert_refused(self._post("not json", raw=True), 422, "VALIDATION_ERROR")

    def test_an_unknown_point_cloud_is_not_found(self) -> None:
        for point_cloud_id in ("pc_missing", "bad.id"):
            with self.subTest(point_cloud_id=point_cloud_id):
                self._assert_refused(
                    self._post({"bounds": REGION}, point_cloud_id), 404, "NOT_FOUND"
                )

    def test_a_point_cloud_whose_file_was_removed_is_gone(self) -> None:
        (self.root / "uploads" / f"{self.source_id}.las").unlink()

        self._assert_refused(self._post({"bounds": REGION}), 410, "GONE")

    def test_a_point_cloud_without_a_file_to_crop_is_a_conflict(self) -> None:
        storage = self.client.app.state.storage
        staging = storage.new_staging_dir("x")
        (staging / "metadata.json").write_text("{}", encoding="utf-8")
        metadata = LasMetadata(
            point_count=5,
            bounds=LasBounds(500000.0, 2000000.0, 10.0, 500100.0, 2000050.0, 20.0),
            crs=None,
        )
        result = DatasetService(storage).create_result(
            self.source_id, "viewer-only.las", metadata, staging
        )

        error = self._assert_refused(
            self._post({"bounds": REGION}, result.id), 409, "CONFLICT"
        )
        self.assertNotIn(str(self.root), json.dumps(error))

    def test_a_region_touching_the_edge_from_inside_is_accepted(self) -> None:
        body = self._region(minX=500000.0, maxX=500001.0, minZ=20.0, maxZ=25.0)

        response = self._post(body)

        self.assertEqual(202, response.status_code, response.text)


if __name__ == "__main__":
    unittest.main()
