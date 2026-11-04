from __future__ import annotations

import tempfile
import threading
import time
import unittest
from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.processing import ProcessingContext, ProcessingResult
from app.processing.errors import ProcessorExecutionError
from las_fixtures import Vlr, build_las, geotiff_key_directory

LAS = build_las(
    point_count=1250000,
    min_xyz=(100.0, 200.0, 0.0),
    max_xyz=(180.5, 260.25, 42.7),
    vlrs=(Vlr("LASF_Projection", 34735, geotiff_key_directory((3072, 32648))),),
)


class FakeProcessor:
    key = "fake"
    input_schema: Mapping[str, object] = {"type": "object"}

    def __init__(self, error: Exception | None = None, hold: bool = False) -> None:
        self.error = error
        self.started = threading.Event()
        self.release = threading.Event()
        if not hold:
            self.release.set()

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test processor was not released")
        if self.error is not None:
            raise self.error
        context.output_directory.mkdir()
        metadata = context.output_directory / "metadata.json"
        metadata.write_text("{}", encoding="utf-8")
        return ProcessingResult(context.output_directory, metadata)


class PointCloudApiTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.settings = Settings(
            storage_root=Path(temporary_directory.name), max_upload_bytes=1024 * 1024
        )

    def _client(self, processor: FakeProcessor | None = None) -> TestClient:
        # Entering the context keeps one event loop alive so background jobs finish.
        client = TestClient(
            create_app(self.settings, processor or FakeProcessor()),
            raise_server_exceptions=False,
        )
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def _upload(self, client: TestClient, filename: str = "survey.laz") -> str:
        response = client.post("/api/upload", files={"file": (filename, LAS)})
        self.assertEqual(201, response.status_code)
        return response.json()["id"]

    def _wait_for(self, client: TestClient, point_cloud_id: str, status: str) -> dict:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            detail = client.get(f"/api/pointcloud/{point_cloud_id}").json()
            if detail["status"] == status:
                return detail
            time.sleep(0.01)
        self.fail(f"point cloud never became {status}")

    def test_returns_the_point_cloud_that_was_uploaded(self) -> None:
        client = self._client()
        uploaded = client.post("/api/upload", files={"file": ("survey.laz", LAS)}).json()

        response = client.get(f"/api/pointcloud/{uploaded['id']}")

        self.assertEqual(200, response.status_code)
        detail = response.json()
        self.assertEqual(uploaded["id"], detail["id"])
        self.assertEqual("survey.laz", detail["filename"])
        self.assertEqual("uploaded", detail["status"])
        self.assertEqual(uploaded["metadata"], detail["metadata"])
        self.assertEqual(1250000, detail["metadata"]["pointCount"])
        self.assertEqual(
            {
                "minX": 100.0,
                "minY": 200.0,
                "minZ": 0.0,
                "maxX": 180.5,
                "maxY": 260.25,
                "maxZ": 42.7,
            },
            detail["metadata"]["bounds"],
        )
        self.assertEqual("EPSG:32648", detail["metadata"]["crs"])

    def test_has_no_viewer_url_or_source_before_conversion(self) -> None:
        client = self._client()
        point_cloud_id = self._upload(client)

        detail = client.get(f"/api/pointcloud/{point_cloud_id}").json()

        self.assertIsNone(detail["viewerUrl"])
        self.assertIsNone(detail["sourceId"])

    def test_shows_the_sanitised_filename_not_the_client_path(self) -> None:
        client = self._client()
        point_cloud_id = self._upload(client, "..\\..\\evil/survey.las")

        detail = client.get(f"/api/pointcloud/{point_cloud_id}").json()

        self.assertEqual("survey.las", detail["filename"])

    def test_unknown_id_uses_the_shared_error_schema(self) -> None:
        client = self._client()

        response = client.get("/api/pointcloud/pc_missing")

        self.assertEqual(404, response.status_code)
        error = response.json()["error"]
        self.assertEqual("NOT_FOUND", error["code"])
        self.assertTrue(error["requestId"].startswith("req_"))
        self.assertEqual(error["requestId"], response.headers["X-Request-ID"])

    def test_ids_that_are_not_dataset_ids_are_not_found(self) -> None:
        client = self._client()

        for dataset_id in ("bad.id", "..", "%2e%2e", "a%20b", "pc_1%00"):
            with self.subTest(dataset_id=dataset_id):
                response = client.get(f"/api/pointcloud/{dataset_id}")
                self.assertIn(response.status_code, (404, 422))

    def test_status_follows_the_conversion(self) -> None:
        processor = FakeProcessor(hold=True)
        client = self._client(processor)
        point_cloud_id = self._upload(client)

        job = client.post(f"/api/pointcloud/{point_cloud_id}/convert").json()
        self.assertTrue(processor.started.wait(timeout=2))
        converting = client.get(f"/api/pointcloud/{point_cloud_id}").json()
        self.assertEqual("converting", converting["status"])
        self.assertIsNone(converting["viewerUrl"])

        processor.release.set()
        ready = self._wait_for(client, point_cloud_id, "ready")

        self.assertEqual(
            f"/api/pointcloud/{point_cloud_id}/viewer/metadata.json", ready["viewerUrl"]
        )
        self.assertEqual("succeeded", client.get(f"/api/job/{job['id']}").json()["state"])

    def test_status_is_failed_when_the_conversion_fails(self) -> None:
        processor = FakeProcessor(ProcessorExecutionError("boom", 1, "stderr"))
        client = self._client(processor)
        point_cloud_id = self._upload(client)

        client.post(f"/api/pointcloud/{point_cloud_id}/convert")
        failed = self._wait_for(client, point_cloud_id, "failed")

        self.assertIsNone(failed["viewerUrl"])
        self.assertNotIn("boom", str(failed))

    def test_the_record_survives_an_application_restart(self) -> None:
        first = self._client()
        point_cloud_id = self._upload(first)

        second = self._client()
        detail = second.get(f"/api/pointcloud/{point_cloud_id}").json()

        self.assertEqual("survey.laz", detail["filename"])
        self.assertEqual("uploaded", detail["status"])

    def test_a_corrupt_record_is_a_server_error_without_details(self) -> None:
        client = self._client()
        point_cloud_id = self._upload(client)
        record = self.settings.storage_root / "metadata" / f"{point_cloud_id}.json"
        record.write_text("{not json", encoding="utf-8")

        response = client.get(f"/api/pointcloud/{point_cloud_id}")

        self.assertEqual(500, response.status_code)
        self.assertEqual("INTERNAL_ERROR", response.json()["error"]["code"])
        self.assertNotIn(str(self.settings.storage_root), response.text)

    def test_a_failed_record_write_leaves_no_upload_and_a_clean_error(self) -> None:
        client = self._client()
        (self.settings.storage_root / "metadata").write_text("not a directory")

        response = client.post("/api/upload", files={"file": ("a.las", LAS)})

        self.assertEqual(500, response.status_code)
        self.assertEqual([], list((self.settings.storage_root / "uploads").iterdir()))
        self.assertNotIn(str(self.settings.storage_root), response.text)


if __name__ == "__main__":
    unittest.main()
