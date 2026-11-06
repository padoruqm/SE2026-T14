from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.processing.errors import ProcessorExecutionError, ProcessorTimeoutError
from las_fixtures import build_las
from test_convert_flow import BlockingProcessor, RecordingProcessor

FINISHED_STATES = ("succeeded", "failed")


class JobApiTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.settings = Settings(
            storage_root=Path(temporary_directory.name), max_upload_bytes=1024 * 1024
        )

    def _client(self, processor) -> TestClient:
        # Entering the context keeps one event loop alive so background jobs finish.
        client = TestClient(create_app(self.settings, processor))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def _convert(self, client: TestClient) -> dict:
        upload = client.post("/api/upload", files={"file": ("a.las", build_las())})
        self.assertEqual(201, upload.status_code)
        point_cloud_id = upload.json()["id"]
        response = client.post(f"/api/pointcloud/{point_cloud_id}/convert")
        self.assertEqual(202, response.status_code)
        return response.json()

    def _wait_until_finished(self, client: TestClient, job_id: str) -> dict:
        # Poll until the job ends, with a deadline instead of a fixed wait.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/job/{job_id}").json()
            if job["state"] in FINISHED_STATES:
                return job
            time.sleep(0.01)
        self.fail("job did not finish")

    def test_enqueue_returns_a_queued_job(self) -> None:
        client = self._client(RecordingProcessor())

        job = self._convert(client)

        self.assertEqual("queued", job["state"])
        self.assertEqual("convert", job["type"])
        self.assertIsNone(job["resultId"])
        self.assertIsNone(job["error"])

    def test_job_goes_from_running_to_succeeded_with_a_result(self) -> None:
        processor = BlockingProcessor()
        client = self._client(processor)
        job = self._convert(client)

        self.assertTrue(processor.started.wait(timeout=2))
        self.assertEqual("running", client.get(f"/api/job/{job['id']}").json()["state"])

        processor.release.set()
        finished = self._wait_until_finished(client, job["id"])

        self.assertEqual("succeeded", finished["state"])
        self.assertEqual(100, finished["progress"])
        self.assertIsNotNone(finished["resultId"])
        self.assertIsNone(finished["error"])

    def test_processor_error_fails_the_job_without_leaking_details(self) -> None:
        error = ProcessorExecutionError(
            "failed at /secret/path", 1, "Traceback (most recent call last)"
        )
        client = self._client(RecordingProcessor(error))
        job = self._convert(client)

        finished = self._wait_until_finished(client, job["id"])

        self.assertEqual("failed", finished["state"])
        self.assertEqual("INTERNAL_ERROR", finished["error"]["code"])
        self.assertNotIn("secret", str(finished))
        self.assertNotIn("Traceback", str(finished))

    def test_processor_timeout_fails_the_job(self) -> None:
        client = self._client(RecordingProcessor(ProcessorTimeoutError("took too long")))
        job = self._convert(client)

        finished = self._wait_until_finished(client, job["id"])

        self.assertEqual("failed", finished["state"])
        self.assertIsNone(finished["resultId"])
        self.assertEqual("INTERNAL_ERROR", finished["error"]["code"])


if __name__ == "__main__":
    unittest.main()
