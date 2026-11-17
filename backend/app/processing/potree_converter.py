from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping
from queue import Empty, Queue
from pathlib import Path
from typing import TextIO

from app.processing.base import (
    ProcessingContext,
    ProcessingResult,
    ProgressCallback,
    Processor,
)
from app.processing.errors import (
    ProcessingInputError,
    ProcessorExecutionError,
    ProcessorTimeoutError,
    ProcessorUnavailableError,
)


_STDERR_LIMIT = 2000
_PROGRESS_PATTERN = re.compile(r"^\s*\[\s*(\d+(?:\.\d+)?)%\s*,")
_OUTPUT_POLL_SECONDS = 0.1


def _progress_from_output(line: str) -> int | None:
    match = _PROGRESS_PATTERN.match(line)
    if match is None:
        return None
    return min(99, int(float(match.group(1))))


def _read_output(stream: TextIO, lines: Queue[str | OSError | None]) -> None:
    try:
        for line in stream:
            lines.put(line)
    except OSError as exc:
        lines.put(exc)
    finally:
        stream.close()
        lines.put(None)


def _stop_process(process: subprocess.Popen[str], reader: threading.Thread) -> None:
    try:
        process.kill()
    except ProcessLookupError:
        pass
    process.wait()
    reader.join()


def _run_converter(
    command: list[str],
    timeout_seconds: float,
    progress_callback: ProgressCallback | None,
) -> tuple[int, str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    if process.stdout is None:
        process.kill()
        process.wait()
        raise ProcessorExecutionError("PotreeConverter output could not be read")

    lines: Queue[str | OSError | None] = Queue()
    reader = threading.Thread(target=_read_output, args=(process.stdout, lines), daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    output_tail = ""

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _stop_process(process, reader)
            raise ProcessorTimeoutError("PotreeConverter exceeded its time limit")

        try:
            line = lines.get(timeout=min(remaining, _OUTPUT_POLL_SECONDS))
        except Empty:
            if process.poll() is not None and not reader.is_alive():
                break
            continue

        if line is None:
            break
        if isinstance(line, OSError):
            _stop_process(process, reader)
            raise ProcessorExecutionError(
                "PotreeConverter output could not be read",
                stderr=output_tail,
            ) from line
        output_tail = (output_tail + line)[-_STDERR_LIMIT:]
        progress = _progress_from_output(line)
        if progress is not None and progress_callback is not None:
            progress_callback(progress)

    try:
        return_code = process.wait(timeout=max(0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        _stop_process(process, reader)
        raise ProcessorTimeoutError("PotreeConverter exceeded its time limit") from None

    reader.join()
    return return_code, output_tail


class PotreeConverterProcessor(Processor):
    key = "potree-converter"
    input_schema: Mapping[str, object] = {
        "type": "object",
        "additionalProperties": False,
    }

    def __init__(
        self, executable: str | None = None, timeout_seconds: float = 300
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._executable = executable or os.getenv(
            "POTREE_CONVERTER_PATH", "PotreeConverter"
        )
        self._timeout_seconds = timeout_seconds

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        if parameters:
            raise ProcessingInputError("Potree conversion does not accept parameters")

        input_path = context.input_path.resolve()
        if input_path.suffix.lower() != ".las":
            raise ProcessingInputError(
                "Potree conversion currently accepts LAS files only"
            )
        if not input_path.is_file():
            raise ProcessingInputError("The input point cloud does not exist")

        output_directory = context.output_directory.resolve()
        try:
            output_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ProcessingInputError(
                "The output directory must not already exist"
            ) from exc

        command = [
            self._executable,
            str(input_path),
            "-o",
            str(output_directory),
        ]
        try:
            return_code, output = _run_converter(
                command,
                self._timeout_seconds,
                context.progress_callback,
            )
        except FileNotFoundError as exc:
            shutil.rmtree(output_directory)
            raise ProcessorUnavailableError(
                "PotreeConverter executable was not found"
            ) from exc
        except ProcessorTimeoutError:
            shutil.rmtree(output_directory)
            raise
        except ProcessorExecutionError:
            shutil.rmtree(output_directory)
            raise
        except OSError as exc:
            shutil.rmtree(output_directory)
            raise ProcessorExecutionError(
                "PotreeConverter could not be started"
            ) from exc

        if return_code != 0:
            shutil.rmtree(output_directory)
            raise ProcessorExecutionError(
                "PotreeConverter exited unsuccessfully",
                return_code=return_code,
                stderr=output,
            )

        metadata_path = output_directory / "metadata.json"
        if not metadata_path.is_file():
            shutil.rmtree(output_directory)
            raise ProcessorExecutionError(
                "PotreeConverter completed without producing metadata.json"
            )

        return ProcessingResult(
            output_directory=output_directory,
            metadata_path=metadata_path,
        )
