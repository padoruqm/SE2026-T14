from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.processing import ProcessingContext, ProcessingResult, Processor
from app.processing.errors import (
    ProcessingInputError,
    ProcessorExecutionError,
    ProcessorTimeoutError,
    ProcessorUnavailableError,
)
from app.processing.pdal_crop import PdalCropProcessor
from app.services.las_metadata import parse_las_metadata
from las_fixtures import build_las


def _sample_las() -> bytes:
    points = b"".join(
        struct.pack("<iiiHBBbBHd", x, y, z, 100, 0x09, 2, 0, 0, 0, 0.0)
        for x, y, z in ((0, 0, 0), (100, 100, 100), (200, 200, 200))
    )
    return build_las(
        point_count=3,
        min_xyz=(0, 0, 0),
        max_xyz=(2, 2, 2),
        payload=points,
    )


def _output_fixture(path: Path) -> None:
    path.write_bytes(
        build_las(
            point_count=1,
            min_xyz=(1, 1, 1),
            max_xyz=(1, 1, 1),
            payload=struct.pack(
                "<iiiHBBbBHd", 100, 100, 100, 100, 0x09, 2, 0, 0, 0, 0.0
            ),
        )
    )


class PdalCropProcessorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.input_path = self.root / "source with spaces;$(echo safe).las"
        self.input_path.write_bytes(_sample_las())
        self.output_directory = self.root / "cropped output"
        self.processor = PdalCropProcessor(executable="pdal", timeout_seconds=12)
        self.parameters = {
            "bounds": {
                "minX": 0.5,
                "minY": 0.5,
                "minZ": 0.5,
                "maxX": 1.5,
                "maxY": 1.5,
                "maxZ": 1.5,
            },
            "output_format": "las",
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _context(self) -> ProcessingContext:
        return ProcessingContext(self.input_path, self.output_directory)

    def _complete_pipeline(self, command, **kwargs):
        self.assertEqual(["pdal", "pipeline", "--stdin"], command)
        self.assertIsInstance(command, list)
        self.assertNotIn("shell", kwargs)
        self.assertEqual(12, kwargs["timeout"])
        self.assertIs(subprocess.PIPE, kwargs["stdout"])
        self.assertIs(subprocess.STDOUT, kwargs["stderr"])
        self.assertTrue(kwargs["text"])

        pipeline = json.loads(kwargs["input"])
        self.assertEqual(str(self.input_path.resolve()), pipeline[0]["filename"])
        self.assertEqual(
            {
                "minx": 0.5,
                "miny": 0.5,
                "minz": 0.5,
                "maxx": 1.5,
                "maxy": 1.5,
                "maxz": 1.5,
            },
            pipeline[1]["bounds"],
        )
        self.assertEqual(
            str((self.output_directory / "cropped.las").resolve()),
            pipeline[2]["filename"],
        )
        self.assertEqual("all", pipeline[2]["forward"])
        _output_fixture(Path(pipeline[2]["filename"]))
        return subprocess.CompletedProcess(command, 0, stdout="crop complete")

    def test_runs_pdal_with_json_pipeline_and_reads_metadata_from_output(self) -> None:
        self.assertIsInstance(self.processor, Processor)
        with patch(
            "app.processing.pdal_crop.subprocess.run",
            side_effect=self._complete_pipeline,
        ):
            result = self.processor.execute(self._context(), self.parameters)

        self.assertEqual(
            ProcessingResult(
                self.output_directory.resolve(),
                self.output_directory.resolve() / "metadata.json",
            ),
            result,
        )
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(1, metadata["point_count"])
        self.assertEqual(
            {
                "minX": 1.0,
                "minY": 1.0,
                "minZ": 1.0,
                "maxX": 1.0,
                "maxY": 1.0,
                "maxZ": 1.0,
            },
            metadata["bounds"],
        )

    def test_enables_compression_for_laz_output(self) -> None:
        parameters = {**self.parameters, "output_format": "laz"}

        def complete_laz(command, **kwargs):
            pipeline = json.loads(kwargs["input"])
            self.assertEqual(
                str((self.output_directory / "cropped.laz").resolve()),
                pipeline[2]["filename"],
            )
            self.assertIs(True, pipeline[2]["compression"])
            _output_fixture(Path(pipeline[2]["filename"]))
            return subprocess.CompletedProcess(command, 0, stdout="")

        with patch(
            "app.processing.pdal_crop.subprocess.run", side_effect=complete_laz
        ):
            result = self.processor.execute(self._context(), parameters)

        self.assertTrue((result.output_directory / "cropped.laz").is_file())

    def test_rejects_non_finite_reversed_and_incomplete_bounds(self) -> None:
        invalid_bounds = [
            {**self.parameters["bounds"], "minX": math.inf},
            {**self.parameters["bounds"], "minX": 10**400},
            {**self.parameters["bounds"], "minY": 2, "maxY": 1},
            {"minX": 0},
        ]
        for bounds in invalid_bounds:
            with self.subTest(bounds=bounds):
                with self.assertRaises(ProcessingInputError):
                    self.processor.execute(
                        self._context(),
                        {**self.parameters, "bounds": bounds},
                    )

    def test_rejects_unknown_parameters_and_output_formats(self) -> None:
        with self.assertRaises(ProcessingInputError):
            self.processor.execute(
                self._context(), {**self.parameters, "outside": True}
            )
        with self.assertRaises(ProcessingInputError):
            self.processor.execute(
                self._context(), {**self.parameters, "output_format": "xyz"}
            )

    def test_rejects_unsupported_or_missing_input(self) -> None:
        unsupported = self.root / "source.txt"
        unsupported.write_text("not a point cloud", encoding="utf-8")
        with self.assertRaises(ProcessingInputError):
            self.processor.execute(
                ProcessingContext(unsupported, self.output_directory), self.parameters
            )
        with self.assertRaises(ProcessingInputError):
            self.processor.execute(
                ProcessingContext(self.root / "missing.las", self.output_directory),
                self.parameters,
            )

    def test_rejects_existing_output_directory(self) -> None:
        self.output_directory.mkdir()
        with self.assertRaises(ProcessingInputError):
            self.processor.execute(self._context(), self.parameters)

    def test_reports_missing_executable_and_cleans_partial_output(self) -> None:
        with patch(
            "app.processing.pdal_crop.subprocess.run", side_effect=FileNotFoundError
        ):
            with self.assertRaises(ProcessorUnavailableError):
                self.processor.execute(self._context(), self.parameters)
        self.assertFalse(self.output_directory.exists())

    def test_reports_timeout_and_cleans_partial_output(self) -> None:
        def timeout(command, **kwargs):
            Path(json.loads(kwargs["input"])[2]["filename"]).write_text(
                "partial", encoding="utf-8"
            )
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="busy")

        with patch("app.processing.pdal_crop.subprocess.run", side_effect=timeout):
            with self.assertRaises(ProcessorTimeoutError):
                self.processor.execute(self._context(), self.parameters)
        self.assertFalse(self.output_directory.exists())

    def test_reports_nonzero_exit_and_cleans_output(self) -> None:
        with patch(
            "app.processing.pdal_crop.subprocess.run",
            return_value=subprocess.CompletedProcess(
                ["pdal"], 7, stdout="processing failed"
            ),
        ):
            with self.assertRaises(ProcessorExecutionError) as raised:
                self.processor.execute(self._context(), self.parameters)
        self.assertEqual(7, raised.exception.return_code)
        self.assertEqual("processing failed", raised.exception.stderr)
        self.assertFalse(self.output_directory.exists())

    def test_rejects_success_without_output(self) -> None:
        with patch(
            "app.processing.pdal_crop.subprocess.run",
            return_value=subprocess.CompletedProcess(["pdal"], 0, stdout=""),
        ):
            with self.assertRaises(ProcessorExecutionError):
                self.processor.execute(self._context(), self.parameters)
        self.assertFalse(self.output_directory.exists())

    def test_rejects_invalid_output_and_cleans_output(self) -> None:
        def complete_without_las(command, **kwargs):
            output_path = Path(json.loads(kwargs["input"])[2]["filename"])
            output_path.write_bytes(b"not a LAS file")
            return subprocess.CompletedProcess(command, 0, stdout="")

        with patch(
            "app.processing.pdal_crop.subprocess.run",
            side_effect=complete_without_las,
        ):
            with self.assertRaises(ProcessorExecutionError):
                self.processor.execute(self._context(), self.parameters)
        self.assertFalse(self.output_directory.exists())

    @unittest.skipUnless(shutil.which("pdal"), "PDAL is not installed")
    def test_crops_las_and_laz_using_installed_pdal(self) -> None:
        for output_format in ("las", "laz"):
            with self.subTest(output_format=output_format):
                self.output_directory = self.root / f"cropped-{output_format}"
                result = self.processor.execute(
                    self._context(),
                    {**self.parameters, "output_format": output_format},
                )
                output_path = result.output_directory / f"cropped.{output_format}"
                metadata = parse_las_metadata(output_path.read_bytes())
                self.assertEqual(1, metadata.point_count)
                self.assertEqual(1.0, metadata.bounds.minX)
                self.assertEqual(1.0, metadata.bounds.maxX)

    def test_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(ValueError):
            PdalCropProcessor(timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
