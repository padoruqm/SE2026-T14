from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.processing.base import ProcessingContext, ProcessingResult, Processor
from app.processing.errors import (
    ProcessingInputError,
    ProcessorExecutionError,
    ProcessorTimeoutError,
    ProcessorUnavailableError,
)
from app.processing.potree_converter import PotreeConverterProcessor


def _write_las_fixture(path: Path) -> None:
    header = struct.pack(
        "<4sHH16sBB32s32sHHHIIBHI5I3d3d6d",
        b"LASF",
        0,
        0,
        bytes(16),
        1,
        2,
        b"SE2026-T14".ljust(32, b"\0"),
        b"test fixture".ljust(32, b"\0"),
        1,
        2026,
        227,
        227,
        0,
        0,
        20,
        2,
        1,
        1,
        0,
        0,
        0,
        0.01,
        0.01,
        0.01,
        0.0,
        0.0,
        0.0,
        2.0,
        1.0,
        2.0,
        1.0,
        0.0,
        0.0,
    )
    points = b"".join(
        struct.pack("<iiiHBBbBH", x, y, z, 100, 0x09, 2, 0, 0, 0)
        for x, y, z in ((100, 100, 0), (200, 200, 100))
    )
    path.write_bytes(header + points)


class PotreeConverterProcessorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.input_path = self.root / "sample with spaces.las"
        self.input_path.write_bytes(b"LASF")
        self.output_directory = self.root / "converted output"
        self.processor = PotreeConverterProcessor(timeout_seconds=12)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _context(self) -> ProcessingContext:
        return ProcessingContext(self.input_path, self.output_directory)

    def test_converter_implements_processing_interface(self) -> None:
        self.assertIsInstance(self.processor, Processor)
        self.assertEqual(
            {"type": "object", "additionalProperties": False},
            self.processor.input_schema,
        )

    def test_runs_converter_with_argument_list_and_timeout(self) -> None:
        def complete_conversion(command, **kwargs):
            Path(command[3], "metadata.json").write_text("{}", encoding="utf-8")
            return_value = subprocess.CompletedProcess(command, 0, "", "")
            self.assertEqual("PotreeConverter", Path(command[0]).name)
            self.assertEqual(str(self.input_path.resolve()), command[1])
            self.assertEqual(["-o", str(self.output_directory.resolve())], command[2:])
            self.assertEqual(12, kwargs["timeout"])
            self.assertFalse(kwargs["check"])
            self.assertIsInstance(command, list)
            return return_value

        with patch(
            "app.processing.potree_converter.subprocess.run",
            side_effect=complete_conversion,
        ):
            result = self.processor.execute(self._context(), {})

        self.assertEqual(
            ProcessingResult(
                self.output_directory.resolve(),
                self.output_directory.resolve() / "metadata.json",
            ),
            result,
        )

    def test_rejects_non_las_input(self) -> None:
        laz_path = self.root / "sample.laz"
        laz_path.write_bytes(b"LASF")

        with self.assertRaises(ProcessingInputError):
            self.processor.execute(
                ProcessingContext(laz_path, self.output_directory), {}
            )

    def test_rejects_missing_input(self) -> None:
        missing_path = self.root / "missing.las"

        with self.assertRaises(ProcessingInputError):
            self.processor.execute(
                ProcessingContext(missing_path, self.output_directory), {}
            )

    def test_rejects_existing_output_directory(self) -> None:
        self.output_directory.mkdir()

        with self.assertRaises(ProcessingInputError):
            self.processor.execute(self._context(), {})

    def test_rejects_parameters_not_declared_by_processor_schema(self) -> None:
        with self.assertRaises(ProcessingInputError):
            self.processor.execute(self._context(), {"method": "shell"})

    def test_reports_missing_executable_and_removes_partial_output(self) -> None:
        with patch(
            "app.processing.potree_converter.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with self.assertRaises(ProcessorUnavailableError):
                self.processor.execute(self._context(), {})

        self.assertFalse(self.output_directory.exists())

    def test_reports_timeout_and_removes_partial_output(self) -> None:
        with patch(
            "app.processing.potree_converter.subprocess.run",
            side_effect=subprocess.TimeoutExpired("PotreeConverter", 12),
        ):
            with self.assertRaises(ProcessorTimeoutError):
                self.processor.execute(self._context(), {})

        self.assertFalse(self.output_directory.exists())

    def test_reports_nonzero_exit_code_and_removes_partial_output(self) -> None:
        with patch(
            "app.processing.potree_converter.subprocess.run",
            return_value=subprocess.CompletedProcess([], 7, "", "failed"),
        ):
            with self.assertRaises(ProcessorExecutionError) as raised:
                self.processor.execute(self._context(), {})

        self.assertEqual(7, raised.exception.return_code)
        self.assertFalse(self.output_directory.exists())

    def test_requires_converter_metadata_output(self) -> None:
        with patch(
            "app.processing.potree_converter.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ):
            with self.assertRaises(ProcessorExecutionError):
                self.processor.execute(self._context(), {})

        self.assertFalse(self.output_directory.exists())

    @unittest.skipUnless(
        shutil.which("PotreeConverter"), "PotreeConverter is not installed"
    )
    def test_converts_a_minimal_las_fixture(self) -> None:
        _write_las_fixture(self.input_path)

        result = self.processor.execute(self._context(), {})

        self.assertTrue(result.metadata_path.is_file())
        self.assertGreater(len(list(result.output_directory.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
