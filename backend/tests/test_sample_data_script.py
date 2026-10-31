from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.services.las_metadata import parse_las_metadata

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate-sample-las.py"
MAX_SAMPLE_BYTES = 20 * 1024 * 1024


class GenerateSampleLasTest(unittest.TestCase):
    def test_generates_a_small_las_with_known_bounds_and_crs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "nested" / "demo.las"
            completed = subprocess.run(
                [sys.executable, str(GENERATOR), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )

            metadata = parse_las_metadata(output.read_bytes()[: 1024 * 1024])
            output_size = output.stat().st_size

        self.assertIn("5 points, EPSG:32648", completed.stdout)
        self.assertLessEqual(output_size, MAX_SAMPLE_BYTES)
        self.assertEqual(5, metadata.point_count)
        self.assertEqual(
            (500_000.0, 2_000_000.0, 100.0, 500_010.0, 2_000_010.0, 105.0),
            (
                metadata.bounds.minX,
                metadata.bounds.minY,
                metadata.bounds.minZ,
                metadata.bounds.maxX,
                metadata.bounds.maxY,
                metadata.bounds.maxZ,
            ),
        )
        self.assertEqual("EPSG:32648", metadata.crs)

    def test_generation_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "first.las"
            second = Path(temporary_directory) / "second.las"

            for output in (first, second):
                subprocess.run(
                    [sys.executable, str(GENERATOR), "--output", str(output)],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()

        self.assertEqual(first_bytes, second_bytes)


if __name__ == "__main__":
    unittest.main()
