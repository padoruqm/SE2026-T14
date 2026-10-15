from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class DatasetApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        settings = Settings(
            storage_root=Path(self.temporary_directory.name),
            max_upload_bytes=8,
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_directory.cleanup()

    def test_upload_stores_dataset(self) -> None:
        response = self.client.post(
            "/api/v1/datasets",
            headers={"X-Filename": "sample.LAS"},
            content=b"LASDATA",
        )

        self.assertEqual(202, response.status_code)
        payload = response.json()
        self.assertEqual("sample.LAS", payload["original_filename"])
        self.assertEqual(7, payload["size_bytes"])
        self.assertEqual("uploaded", payload["status"])

        stored_files = list(
            (Path(self.temporary_directory.name) / "uploads").glob("*.las")
        )
        self.assertEqual(1, len(stored_files))
        self.assertEqual(b"LASDATA", stored_files[0].read_bytes())

    def test_rejects_unsupported_extension(self) -> None:
        response = self.client.post(
            "/api/v1/datasets",
            headers={"X-Filename": "notes.txt"},
            content=b"text",
        )

        self.assertEqual(415, response.status_code)

    def test_rejects_upload_over_limit_without_leaving_partial_file(self) -> None:
        response = self.client.post(
            "/api/v1/datasets",
            headers={"X-Filename": "large.laz"},
            content=b"123456789",
        )

        self.assertEqual(413, response.status_code)
        upload_root = Path(self.temporary_directory.name) / "uploads"
        self.assertEqual([], list(upload_root.iterdir()))

if __name__ == "__main__":
    unittest.main()
