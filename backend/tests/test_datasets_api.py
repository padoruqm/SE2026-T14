from __future__ import annotations

import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from las_fixtures import Vlr, build_las, geotiff_key_directory

LAS_BYTES = build_las(point_count=2, min_xyz=(1.0, 2.0, 0.0), max_xyz=(3.0, 4.0, 5.0))
MAX_UPLOAD_BYTES = 4096
EXPORT_EXPECTED_BOUNDS = {
    "minX": 500_001.25,
    "minY": 2_000_002.5,
    "minZ": 100.75,
    "maxX": 500_004.25,
    "maxY": 2_000_006.5,
    "maxZ": 112.75,
}


def _export_fixture_las() -> bytes:
    points = ((125, 250, 75), (425, 650, 1275))
    payload = b"".join(
        struct.pack("<iiiHBBbBHd", x, y, z, 100, 0x09, 2, 0, 0, 0, 0.0)
        for x, y, z in points
    )
    return build_las(
        point_count=len(points),
        scale=(0.01, 0.01, 0.01),
        offset=(500_000.0, 2_000_000.0, 100.0),
        min_xyz=(
            EXPORT_EXPECTED_BOUNDS["minX"],
            EXPORT_EXPECTED_BOUNDS["minY"],
            EXPORT_EXPECTED_BOUNDS["minZ"],
        ),
        max_xyz=(
            EXPORT_EXPECTED_BOUNDS["maxX"],
            EXPORT_EXPECTED_BOUNDS["maxY"],
            EXPORT_EXPECTED_BOUNDS["maxZ"],
        ),
        vlrs=(
            Vlr(
                "LASF_Projection",
                34735,
                geotiff_key_directory(
                    (1024, 1), (1025, 1), (2048, 4326), (3072, 32648)
                ),
            ),
        ),
        payload=payload,
    )


class UploadApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        settings = Settings(
            storage_root=Path(self.temporary_directory.name),
            max_upload_bytes=MAX_UPLOAD_BYTES,
        )
        self.client = TestClient(create_app(settings), raise_server_exceptions=False)
        self.upload_root = Path(self.temporary_directory.name) / "uploads"
        self.converted_root = Path(self.temporary_directory.name) / "converted"

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

    def test_download_streams_ready_las_and_laz_with_the_original_filename(self) -> None:
        for filename in ("survey.las", "survey.laz"):
            with self.subTest(filename=filename):
                upload = self._upload(filename, LAS_BYTES)
                point_cloud_id = upload.json()["id"]
                (self.converted_root / point_cloud_id).mkdir(parents=True)

                response = self.client.get(
                    f"/api/pointcloud/{point_cloud_id}/download"
                )

                self.assertEqual(200, response.status_code)
                self.assertEqual(
                    "application/octet-stream", response.headers["content-type"]
                )
                self.assertEqual(
                    f'attachment; filename="{filename}"',
                    response.headers["content-disposition"],
                )
                self.assertEqual(LAS_BYTES, response.content)

    def test_downloaded_las_and_laz_are_readable_by_pdal_and_match_metadata(
        self,
    ) -> None:
        pdal_executable = shutil.which("pdal")
        if pdal_executable is None:
            self.skipTest("PDAL CLI is not available on PATH")

        root = Path(self.temporary_directory.name)
        source_las = root / "export-fixture.las"
        source_las.write_bytes(_export_fixture_las())
        source_files = {"survey.las": source_las}

        source_laz = root / "export-fixture.laz"
        translate = subprocess.run(
            [pdal_executable, "pipeline", "--stdin"],
            input=json.dumps(
                {
                    "pipeline": [
                        {"type": "readers.las", "filename": str(source_las)},
                        {
                            "type": "writers.las",
                            "filename": str(source_laz),
                            "compression": True,
                            "forward": "all",
                        },
                    ]
                }
            ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, translate.returncode, translate.stdout + translate.stderr)
        source_files["survey.laz"] = source_laz

        for filename, source_path in source_files.items():
            with self.subTest(filename=filename):
                upload = self._upload(filename, source_path.read_bytes())
                point_cloud_id = upload.json()["id"]
                self.assertEqual(
                    {
                        "pointCount": 2,
                        "bounds": EXPORT_EXPECTED_BOUNDS,
                        "crs": "EPSG:32648",
                    },
                    upload.json()["metadata"],
                )
                (self.converted_root / point_cloud_id).mkdir(parents=True)

                response = self.client.get(
                    f"/api/pointcloud/{point_cloud_id}/download"
                )

                self.assertEqual(200, response.status_code)
                self.assertEqual(source_path.read_bytes(), response.content)
                downloaded_path = root / f"downloaded-{filename}"
                downloaded_path.write_bytes(response.content)
                info = subprocess.run(
                    [pdal_executable, "info", "--summary", str(downloaded_path)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, info.returncode, info.stdout + info.stderr)
                summary = json.loads(info.stdout)["summary"]
                self.assertEqual(2, summary["num_points"])
                for axis in "XYZ":
                    with self.subTest(filename=filename, axis=axis):
                        self.assertEqual(
                            EXPORT_EXPECTED_BOUNDS[f"min{axis}"],
                            summary["bounds"][axis]["min"],
                        )
                        self.assertEqual(
                            EXPORT_EXPECTED_BOUNDS[f"max{axis}"],
                            summary["bounds"][axis]["max"],
                        )

    def test_download_of_a_point_cloud_that_is_not_ready_returns_conflict(self) -> None:
        upload = self._upload("survey.las", LAS_BYTES)

        response = self.client.get(
            f"/api/pointcloud/{upload.json()['id']}/download"
        )

        self._assert_error(response, 409, "CONFLICT")
        self.assertIn("not ready", response.json()["error"]["message"].lower())

    def test_download_of_an_unknown_point_cloud_returns_not_found(self) -> None:
        response = self.client.get("/api/pointcloud/pc_missing/download")

        self._assert_error(response, 404, "NOT_FOUND")

    def test_download_of_a_ready_dataset_without_its_file_returns_gone(self) -> None:
        upload = self._upload("survey.las", LAS_BYTES)
        point_cloud_id = upload.json()["id"]
        (self.converted_root / point_cloud_id).mkdir(parents=True)
        (self.upload_root / f"{point_cloud_id}.las").unlink()

        response = self.client.get(
            f"/api/pointcloud/{point_cloud_id}/download"
        )

        self._assert_error(response, 410, "GONE")

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
