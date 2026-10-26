from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.processing.converter import ConversionError, PotreeConverter
from las_fixtures import build_las

LAS_BYTES = build_las()


class RecordingConverter:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[Path] = []

    async def convert(self, source: Path, output_dir: Path) -> None:
        self.calls.append(source)
        if self.error is not None:
            raise self.error
        (output_dir / "metadata.json").write_text("{}", encoding="utf-8")


class ConvertFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.settings = Settings(storage_root=self.root, max_upload_bytes=1024 * 1024)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _client(self, converter) -> TestClient:
        # Entering the context keeps one event loop alive so background jobs finish.
        client = TestClient(create_app(self.settings, converter))
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
        converter = RecordingConverter()
        client = self._client(converter)
        point_cloud_id = self._upload(client)

        response = client.post(f"/api/pointcloud/{point_cloud_id}/convert")

        self.assertEqual(202, response.status_code)
        accepted = response.json()
        self.assertTrue(accepted["id"].startswith("job_"))
        self.assertEqual("convert", accepted["type"])
        job = self._wait_for_job(client, accepted["id"])
        self.assertEqual("succeeded", job["state"])
        self.assertEqual(100, job["progress"])
        self.assertEqual(point_cloud_id, job["resultId"])
        self.assertIsNone(job["error"])
        self.assertEqual(
            [self.root / "uploads" / f"{point_cloud_id}.las"], converter.calls
        )
        self.assertTrue((self.root / "converted" / point_cloud_id / "metadata.json").is_file())
        self.assertEqual([], [p for p in (self.root / "converted").iterdir() if p.name.startswith(".")])

    def test_failed_conversion_reports_the_error_and_leaves_no_result(self) -> None:
        converter = RecordingConverter(
            ConversionError("INVALID_POINT_CLOUD", "The point cloud could not be converted")
        )
        client = self._client(converter)
        point_cloud_id = self._upload(client)

        job_id = client.post(f"/api/pointcloud/{point_cloud_id}/convert").json()["id"]
        job = self._wait_for_job(client, job_id)

        self.assertEqual("failed", job["state"])
        self.assertIsNone(job["resultId"])
        self.assertEqual("INVALID_POINT_CLOUD", job["error"]["code"])
        self.assertEqual([], list((self.root / "converted").iterdir()))

    def test_unexpected_converter_error_hides_internal_details(self) -> None:
        client = self._client(RecordingConverter(RuntimeError("/secret/path")))
        point_cloud_id = self._upload(client)

        job_id = client.post(f"/api/pointcloud/{point_cloud_id}/convert").json()["id"]
        job = self._wait_for_job(client, job_id)

        self.assertEqual("failed", job["state"])
        self.assertEqual("INTERNAL_ERROR", job["error"]["code"])
        self.assertNotIn("secret", str(job))

    def test_convert_unknown_point_cloud_returns_not_found(self) -> None:
        client = self._client(RecordingConverter())

        response = client.post("/api/pointcloud/pc_missing/convert")

        self.assertEqual(404, response.status_code)
        self.assertEqual("NOT_FOUND", response.json()["error"]["code"])

    def test_convert_rejects_ids_that_escape_the_upload_folder(self) -> None:
        client = self._client(RecordingConverter())

        response = client.post("/api/pointcloud/..%2F..%2Fetc/convert")

        self.assertEqual(404, response.status_code)

    def test_second_convert_conflicts_unless_forced(self) -> None:
        converter = RecordingConverter()
        client = self._client(converter)
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
        self.assertEqual(2, len(converter.calls))

    def test_get_unknown_job_returns_not_found(self) -> None:
        client = self._client(RecordingConverter())

        response = client.get("/api/job/job_missing")

        self.assertEqual(404, response.status_code)
        self.assertEqual("NOT_FOUND", response.json()["error"]["code"])

    def test_rejected_upload_creates_nothing_to_convert(self) -> None:
        client = self._client(RecordingConverter())

        response = client.post("/api/upload", files={"file": ("a.las", b"NOTLAS-DATA")})

        self.assertEqual(422, response.status_code)
        self.assertEqual(404, client.post("/api/pointcloud/pc_x/convert").status_code)


class PotreeConverterTest(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_executable_fails_with_internal_error(self) -> None:
        with self.assertRaises(ConversionError) as context:
            await PotreeConverter(None, 1).convert(Path("in.las"), Path("out"))

        self.assertEqual("INTERNAL_ERROR", context.exception.code)

    async def test_missing_executable_fails_with_internal_error(self) -> None:
        with self.assertRaises(ConversionError) as context:
            await PotreeConverter("/nonexistent/converter", 1).convert(
                Path("in.las"), Path("out")
            )

        self.assertEqual("INTERNAL_ERROR", context.exception.code)

    async def test_non_zero_exit_code_is_an_invalid_point_cloud(self) -> None:
        with self.assertRaises(ConversionError) as context:
            await PotreeConverter("false", 5).convert(Path("in.las"), Path("out"))

        self.assertEqual("INVALID_POINT_CLOUD", context.exception.code)

    async def test_successful_exit_code_passes(self) -> None:
        await PotreeConverter("true", 5).convert(Path("in.las"), Path("out"))

    async def test_timeout_kills_the_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "slow.sh"
            script.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
            script.chmod(0o755)
            with self.assertRaises(ConversionError) as context:
                await PotreeConverter(str(script), 0.1).convert(
                    Path("in.las"), Path("out")
                )

        self.assertEqual("INTERNAL_ERROR", context.exception.code)


if __name__ == "__main__":
    unittest.main()
