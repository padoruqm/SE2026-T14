from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
from io import StringIO
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


class FakeProcess:
    def __init__(self, output: str = "", return_code: int = 0) -> None:
        self.stdout = StringIO(output)
        self.return_code = return_code

    def poll(self) -> int:
        return self.return_code

    def wait(self, timeout: float | None = None) -> int:
        return self.return_code

    def kill(self) -> None:
        self.return_code = -9


class BlockingOutput:
    def __init__(self, release: threading.Event) -> None:
        self.release = release

    def __iter__(self):
        self.release.wait(timeout=2)
        return iter(())

    def close(self) -> None:
        self.release.set()


class BlockingProcess(FakeProcess):
    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()
        self.stdout = BlockingOutput(self.release)

    def wait(self, timeout: float | None = None) -> int:
        self.release.set()
        return super().wait(timeout)

    def kill(self) -> None:
        self.release.set()
        super().kill()


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

    def test_runs_converter_with_argument_list_and_reports_progress(self) -> None:
        progress: list[int] = []

        def complete_conversion(command, **kwargs):
            Path(command[3], "metadata.json").write_text("{}", encoding="utf-8")
            self.assertEqual("PotreeConverter", Path(command[0]).name)
            self.assertEqual(str(self.input_path.resolve()), command[1])
            self.assertEqual(["-o", str(self.output_directory.resolve())], command[2:])
            self.assertIs(subprocess.PIPE, kwargs["stdout"])
            self.assertIs(subprocess.STDOUT, kwargs["stderr"])
            self.assertTrue(kwargs["text"])
            self.assertIsInstance(command, list)
            return FakeProcess(
                "[0.0%, 1.0s], [chunking: 0.0%]\n"
                "[42.8%, 2.0s], [chunking: 50.0%]\n"
                "conversion finished\n"
            )

        with patch(
            "app.processing.potree_converter.subprocess.Popen",
            side_effect=complete_conversion,
        ):
            result = self.processor.execute(
                ProcessingContext(
                    self.input_path,
                    self.output_directory,
                    progress_callback=progress.append,
                ),
                {},
            )

        self.assertEqual(
            ProcessingResult(
                self.output_directory.resolve(),
                self.output_directory.resolve() / "metadata.json",
            ),
            result,
        )
        self.assertEqual([0, 42], progress)

    def test_ignores_unrecognized_progress_output_and_never_reports_100_early(self) -> None:
        progress: list[int] = []

        def complete_conversion(command, **kwargs):
            Path(command[3], "metadata.json").write_text("{}", encoding="utf-8")
            return FakeProcess(
                "starting conversion\n"
                "[100.0%, 2.0s], [indexing: 100.0%]\n"
            )

        with patch(
            "app.processing.potree_converter.subprocess.Popen",
            side_effect=complete_conversion,
        ):
            self.processor.execute(
                ProcessingContext(
                    self.input_path,
                    self.output_directory,
                    progress_callback=progress.append,
                ),
                {},
            )

        self.assertEqual([99], progress)

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
            "app.processing.potree_converter.subprocess.Popen",
            side_effect=FileNotFoundError,
        ):
            with self.assertRaises(ProcessorUnavailableError):
                self.processor.execute(self._context(), {})

        self.assertFalse(self.output_directory.exists())

    def test_reports_timeout_and_removes_partial_output(self) -> None:
        self.processor._timeout_seconds = 0.01
        with patch(
            "app.processing.potree_converter.subprocess.Popen",
            return_value=BlockingProcess(),
        ):
            with self.assertRaises(ProcessorTimeoutError):
                self.processor.execute(self._context(), {})

        self.assertFalse(self.output_directory.exists())

    def test_reports_nonzero_exit_code_and_removes_partial_output(self) -> None:
        with patch(
            "app.processing.potree_converter.subprocess.Popen",
            return_value=FakeProcess("failed\n", 7),
        ):
            with self.assertRaises(ProcessorExecutionError) as raised:
                self.processor.execute(self._context(), {})

        self.assertEqual(7, raised.exception.return_code)
        self.assertFalse(self.output_directory.exists())

    def test_requires_converter_metadata_output(self) -> None:
        with patch(
            "app.processing.potree_converter.subprocess.Popen",
            return_value=FakeProcess(),
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
