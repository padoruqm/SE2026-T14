from __future__ import annotations

import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.errors import InvalidPointCloudError
from app.services.datasets import DatasetService
from app.storage.local import LocalDatasetStorage
from las_fixtures import Vlr, build_las, geotiff_key_directory


async def _chunked(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


class DatasetServiceStreamingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.upload_root = root / "uploads"
        self.service = DatasetService(LocalDatasetStorage(root, max_upload_bytes=1 << 20))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_reads_metadata_when_the_header_arrives_in_tiny_chunks(self) -> None:
        keys = geotiff_key_directory((3072, 32648))
        las = build_las(
            point_count=7,
            vlrs=(Vlr("LASF_Projection", 34735, keys),),
            payload=b"p" * 300,
        )

        stored = await self.service.store_upload("tiny.las", _chunked(las, 5))

        self.assertEqual(7, stored.metadata.point_count)
        self.assertEqual("EPSG:32648", stored.metadata.crs)
        saved = next(self.upload_root.glob("*.las"))
        self.assertEqual(las, saved.read_bytes())

    async def test_header_split_across_the_signature_is_still_validated(self) -> None:
        with self.assertRaises(InvalidPointCloudError):
            await self.service.store_upload("fake.las", _chunked(b"NOTLAS" * 100, 2))

        self.assertEqual([], list(self.upload_root.iterdir()))

    async def test_stream_ending_inside_the_header_is_rejected(self) -> None:
        las = build_las()

        with self.assertRaises(InvalidPointCloudError):
            await self.service.store_upload("cut.las", _chunked(las[:120], 16))

        self.assertEqual([], list(self.upload_root.iterdir()))


if __name__ == "__main__":
    unittest.main()
