from __future__ import annotations

import os
import shutil
import struct
import tempfile
import threading
import time
import unittest
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.processing import PotreeConverterProcessor, ProcessingContext, ProcessingResult
from app.processing.errors import ProcessingInputError, ProcessorExecutionError
from app.storage.local import LocalDatasetStorage
from las_fixtures import build_las

LAS_BYTES = build_las()


def build_las_with_points() -> bytes:
    points = b"".join(
        struct.pack("<iiiHBBbBHd", x, y, z, 100, 0x09, 2, 0, 0, 0, 0.0)
        for x, y, z in ((100, 100, 0), (200, 200, 100))
    )
    return build_las(payload=points)


class RecordingProcessor:
    key = "recording"
    input_schema: Mapping[str, object] = {"type": "object"}

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[Path] = []

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        self.calls.append(context.input_path)
        if self.error is not None:
            raise self.error
        context.output_directory.mkdir()
        metadata = context.output_directory / "metadata.json"
        metadata.write_text("{}", encoding="utf-8")
        return ProcessingResult(context.output_directory, metadata)


class BlockingProcessor(RecordingProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test processor was not released")
        return super().execute(context, parameters)


class ConvertFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.settings = Settings(storage_root=self.root, max_upload_bytes=1024 * 1024)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _client(self, processor) -> TestClient:
        # Entering the context keeps one event loop alive so background jobs finish.
        client = TestClient(create_app(self.settings, processor))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def _upload(self, client: TestClient) -> str:
        response = client.post("/api/upload", files={"file": ("a.las", LAS_BYTES)})
        self.assertEqual(201, response.status_code)
        return response.json()["id"]

    def _wait_for_job(self, client: TestClient, job_id: str) -> dict:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/job/{job_id}").json()
            if job["state"] in ("succeeded", "failed"):
                return job
            time.sleep(0.01)
        self.fail("job did not finish")

    def test_uploaded_file_converts_end_to_end(self) -> None:
        processor = RecordingProcessor()
        client = self._client(processor)
        point_cloud_id = self._upload(client)

        with self.assertLogs("app.jobs.runner", level="INFO") as captured:
            response = client.post(f"/api/pointcloud/{point_cloud_id}/convert")
            self.assertEqual(202, response.status_code)
            accepted = response.json()
            self.assertTrue(accepted["id"].startswith("job_"))
            self.assertEqual("convert", accepted["type"])
            job = self._wait_for_job(client, accepted["id"])

        self.assertTrue(
            any(record.job_id == accepted["id"] for record in captured.records)
        )
        self.assertEqual("succeeded", job["state"])
        self.assertEqual(100, job["progress"])
        self.assertEqual(point_cloud_id, job["resultId"])
        self.assertIsNone(job["error"])
        self.assertEqual(
            [self.root / "uploads" / f"{point_cloud_id}.las"], processor.calls
        )
        self.assertTrue((self.root / "converted" / point_cloud_id / "metadata.json").is_file())
        self.assertEqual([], [p for p in (self.root / "converted").iterdir() if p.name.startswith(".")])

    def test_synchronous_processor_does_not_block_job_api_requests(self) -> None:
        processor = BlockingProcessor()
        client = self._client(processor)
        point_cloud_id = self._upload(client)

        with ThreadPoolExecutor(max_workers=2) as executor:
            convert = executor.submit(
                client.post, f"/api/pointcloud/{point_cloud_id}/convert"
            )
            try:
                self.assertTrue(processor.started.wait(timeout=2))
                response = convert.result(timeout=2)
                self.assertEqual(202, response.status_code)
                job_id = response.json()["id"]

                status_response = executor.submit(
                    client.get, f"/api/job/{job_id}"
                ).result(timeout=2)
                self.assertEqual(200, status_response.status_code)
                self.assertEqual("running", status_response.json()["state"])
            finally:
                processor.release.set()

        self.assertEqual("succeeded", self._wait_for_job(client, job_id)["state"])

    def test_failed_conversion_reports_the_error_and_leaves_no_result(self) -> None:
        processor = RecordingProcessor(ProcessingInputError("not a LAS file"))
        client = self._client(processor)
        point_cloud_id = self._upload(client)

        job_id = client.post(f"/api/pointcloud/{point_cloud_id}/convert").json()["id"]
        job = self._wait_for_job(client, job_id)

        self.assertEqual("failed", job["state"])
        self.assertIsNone(job["resultId"])
        self.assertEqual("INVALID_POINT_CLOUD", job["error"]["code"])
        self.assertEqual([], list((self.root / "converted").iterdir()))

    def test_processor_crash_is_an_internal_error_not_an_invalid_file(self) -> None:
        client = self._client(
            RecordingProcessor(ProcessorExecutionError("boom", 1, "stderr text"))
        )
        point_cloud_id = self._upload(client)

        with self.assertLogs("app.jobs.runner", level="ERROR") as captured:
            job_id = client.post(
                f"/api/pointcloud/{point_cloud_id}/convert"
            ).json()["id"]
            job = self._wait_for_job(client, job_id)

        self.assertEqual("failed", job["state"])
        self.assertEqual("INTERNAL_ERROR", job["error"]["code"])
        self.assertNotIn("stderr text", str(job))
        self.assertTrue(any(record.job_id == job_id for record in captured.records))

    def test_unexpected_converter_error_hides_internal_details(self) -> None:
        client = self._client(RecordingProcessor(RuntimeError("/secret/path")))
        point_cloud_id = self._upload(client)

        job_id = client.post(f"/api/pointcloud/{point_cloud_id}/convert").json()["id"]
        job = self._wait_for_job(client, job_id)

        self.assertEqual("failed", job["state"])
        self.assertEqual("INTERNAL_ERROR", job["error"]["code"])
        self.assertNotIn("secret", str(job))

    def test_convert_unknown_point_cloud_returns_not_found(self) -> None:
        client = self._client(RecordingProcessor())

        response = client.post("/api/pointcloud/pc_missing/convert")

        self.assertEqual(404, response.status_code)
        self.assertEqual("NOT_FOUND", response.json()["error"]["code"])

    def test_convert_rejects_ids_that_escape_the_upload_folder(self) -> None:
        client = self._client(RecordingProcessor())

        response = client.post("/api/pointcloud/..%2F..%2Fetc/convert")

        self.assertEqual(404, response.status_code)

    def test_second_convert_conflicts_unless_forced(self) -> None:
        processor = RecordingProcessor()
        client = self._client(processor)
        point_cloud_id = self._upload(client)
        job_id = client.post(f"/api/pointcloud/{point_cloud_id}/convert").json()["id"]
        self._wait_for_job(client, job_id)

        conflict = client.post(f"/api/pointcloud/{point_cloud_id}/convert")
        forced = client.post(
            f"/api/pointcloud/{point_cloud_id}/convert", json={"force": True}
        )

        self.assertEqual(409, conflict.status_code)
        self.assertEqual("CONFLICT", conflict.json()["error"]["code"])
        self.assertEqual(202, forced.status_code)
        self.assertEqual("succeeded", self._wait_for_job(client, forced.json()["id"])["state"])
        self.assertEqual(2, len(processor.calls))

    def test_get_unknown_job_returns_not_found(self) -> None:
        client = self._client(RecordingProcessor())

        response = client.get("/api/job/job_missing")

        self.assertEqual(404, response.status_code)
        self.assertEqual("NOT_FOUND", response.json()["error"]["code"])

    def test_rejected_upload_creates_nothing_to_convert(self) -> None:
        client = self._client(RecordingProcessor())

        response = client.post("/api/upload", files={"file": ("a.las", b"NOTLAS-DATA")})

        self.assertEqual(422, response.status_code)
        self.assertEqual(404, client.post("/api/pointcloud/pc_x/convert").status_code)


class PublishConvertedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.addCleanup(self.temporary_directory.cleanup)
        self.storage = LocalDatasetStorage(self.root, 1024)

    def _staged(self, content: str) -> Path:
        staging = self.storage.new_staging_dir("pc_a")
        result = staging / "result"
        result.mkdir()
        (result / "metadata.json").write_text(content, encoding="utf-8")
        return result

    def test_publish_replaces_the_old_result_and_leaves_nothing_behind(self) -> None:
        self.storage.publish_converted("pc_a", self._staged("old"))
        self.storage.publish_converted("pc_a", self._staged("new"))

        converted = self.root / "converted"
        self.assertEqual(
            "new", (converted / "pc_a" / "metadata.json").read_text(encoding="utf-8")
        )
        leftovers = [p.name for p in converted.iterdir() if p.name.startswith(".pc_a-old")]
        self.assertEqual([], leftovers)

    def test_failed_publish_keeps_the_old_result(self) -> None:
        self.storage.publish_converted("pc_a", self._staged("old"))

        with self.assertRaises(FileNotFoundError):
            self.storage.publish_converted("pc_a", self.root / "missing")

        self.assertEqual(
            "old",
            (self.root / "converted" / "pc_a" / "metadata.json").read_text(
                encoding="utf-8"
            ),
        )


@unittest.skipUnless(
    shutil.which(os.getenv("POTREE_CONVERTER_PATH", "PotreeConverter")),
    "PotreeConverter is not installed",
)
class RealConverterFlowTest(unittest.TestCase):
    setUp = ConvertFlowTest.setUp
    tearDown = ConvertFlowTest.tearDown
    _client = ConvertFlowTest._client
    _upload = ConvertFlowTest._upload
    _wait_for_job = ConvertFlowTest._wait_for_job

    def test_real_converter_produces_a_viewer_resource(self) -> None:
        client = self._client(PotreeConverterProcessor())
        response = client.post(
            "/api/upload",
            files={"file": ("converter-test.las", build_las_with_points())},
        )
        self.assertEqual(201, response.status_code)
        point_cloud_id = response.json()["id"]

        job_id = client.post(f"/api/pointcloud/{point_cloud_id}/convert").json()["id"]
        job = self._wait_for_job(client, job_id)

        self.assertEqual("succeeded", job["state"], job)
        self.assertTrue(
            (self.root / "converted" / point_cloud_id / "metadata.json").is_file()
        )


if __name__ == "__main__":
    unittest.main()
