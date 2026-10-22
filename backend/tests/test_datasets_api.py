from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from las_fixtures import Vlr, build_las, geotiff_key_directory

LAS_BYTES = build_las(point_count=2, min_xyz=(1.0, 2.0, 0.0), max_xyz=(3.0, 4.0, 5.0))
MAX_UPLOAD_BYTES = 4096


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
            {
                "pointCount": 2,
                "bounds": {
                    "minX": 1.0,
                    "minY": 2.0,
                    "minZ": 0.0,
                    "maxX": 3.0,
                    "maxY": 4.0,
                    "maxZ": 5.0,
                },
                "crs": None,
            },
            payload["metadata"],
        )

    def test_upload_returns_the_crs_declared_in_the_header(self) -> None:
        keys = geotiff_key_directory((3072, 32648))
        las = build_las(vlrs=(Vlr("LASF_Projection", 34735, keys),))

        response = self._upload("utm.laz", las)

        self.assertEqual("EPSG:32648", response.json()["metadata"]["crs"])

    def test_upload_stores_the_file_under_a_server_generated_name(self) -> None:
        payload = self._upload("client-chosen.las", LAS_BYTES).json()

        stored_names = [path.name for path in self.upload_root.iterdir()]
        self.assertEqual([f"{payload['id']}.las"], stored_names)

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

    def test_rejects_a_file_with_a_valid_signature_but_truncated_header(self) -> None:
        response = self._upload("truncated.las", LAS_BYTES[:150])

        self._assert_error(response, 422, "INVALID_POINT_CLOUD")
        self.assertEqual([], list(self.upload_root.iterdir()))

    def test_rejects_a_header_with_inverted_bounds(self) -> None:
        las = build_las(min_xyz=(9.0, 0.0, 0.0), max_xyz=(1.0, 1.0, 1.0))

        response = self._upload("bad.las", las)

        self._assert_error(response, 422, "INVALID_POINT_CLOUD")
        self.assertEqual([], list(self.upload_root.iterdir()))

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
