from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

LAS_BYTES = b"LASF" + b"\x00" * 4
MAX_UPLOAD_BYTES = 16


class UploadApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        settings = Settings(
            storage_root=Path(self.temporary_directory.name),
            max_upload_bytes=MAX_UPLOAD_BYTES,
        )
        self.client = TestClient(create_app(settings), raise_server_exceptions=False)
        self.upload_root = Path(self.temporary_directory.name) / "uploads"

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_directory.cleanup()

    def _upload(self, filename: str, content: bytes):
        return self.client.post(
            "/api/upload", files={"file": (filename, content)}
        )

    def _assert_error(self, response, status_code: int, code: str) -> None:
        self.assertEqual(status_code, response.status_code)
        error = response.json()["error"]
        self.assertEqual(code, error["code"])
        self.assertTrue(error["message"])
        self.assertTrue(error["requestId"].startswith("req_"))
        self.assertIsInstance(error["details"], dict)
        self.assertEqual(error["requestId"], response.headers["X-Request-ID"])

    def test_upload_returns_created_point_cloud_resource(self) -> None:
        response = self._upload("sample.LAS", LAS_BYTES)

        self.assertEqual(201, response.status_code)
        payload = response.json()
        self.assertTrue(payload["id"].startswith("pc_"))
        self.assertEqual("sample.LAS", payload["filename"])
        self.assertEqual("uploaded", payload["status"])
        self.assertEqual(
            {"pointCount": None, "bounds": None, "crs": None}, payload["metadata"]
        )

    def test_upload_stores_file_bytes(self) -> None:
        self._upload("sample.las", LAS_BYTES)

        stored_files = list(self.upload_root.glob("*.las"))
        self.assertEqual(1, len(stored_files))
        self.assertEqual(LAS_BYTES, stored_files[0].read_bytes())

    def test_upload_strips_client_path_from_filename(self) -> None:
        response = self._upload("..\\..\\evil/survey.laz", LAS_BYTES)

        self.assertEqual("survey.laz", response.json()["filename"])

    def test_rejects_unsupported_extension(self) -> None:
        response = self._upload("notes.txt", LAS_BYTES)

        self._assert_error(response, 415, "UNSUPPORTED_FILE_TYPE")

    def test_rejects_invalid_las_signature(self) -> None:
        response = self._upload("fake.las", b"NOTLAS-DATA")

        self._assert_error(response, 422, "INVALID_POINT_CLOUD")

    def test_rejects_file_shorter_than_signature(self) -> None:
        response = self._upload("short.laz", b"LA")

        self._assert_error(response, 422, "INVALID_POINT_CLOUD")

    def test_rejects_empty_file(self) -> None:
        response = self._upload("empty.las", b"")

        self._assert_error(response, 422, "INVALID_POINT_CLOUD")

    def test_invalid_signature_leaves_no_file_behind(self) -> None:
        self._upload("fake.las", b"NOTLAS-DATA")

        self.assertEqual([], list(self.upload_root.iterdir()))

    def test_rejects_upload_over_limit_without_leaving_partial_file(self) -> None:
        response = self._upload("large.laz", LAS_BYTES + b"0" * MAX_UPLOAD_BYTES)

        self._assert_error(response, 413, "FILE_TOO_LARGE")
        self.assertEqual([], list(self.upload_root.iterdir()))

    def test_missing_file_field_returns_validation_error(self) -> None:
        response = self.client.post("/api/upload", data={"other": "value"})

        self._assert_error(response, 422, "VALIDATION_ERROR")

    def test_unknown_route_uses_shared_error_schema(self) -> None:
        response = self.client.get("/api/pointcloud/missing")

        self._assert_error(response, 404, "NOT_FOUND")

    def test_unexpected_error_hides_internal_details(self) -> None:
        async def boom() -> None:
            raise RuntimeError("/secret/server/path")

        self.client.app.add_api_route("/api/boom", boom)

        response = self.client.get("/api/boom")

        self._assert_error(response, 500, "INTERNAL_ERROR")
        self.assertNotIn("secret", response.text)


if __name__ == "__main__":
    unittest.main()
