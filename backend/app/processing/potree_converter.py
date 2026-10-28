from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from app.processing.base import ProcessingContext, ProcessingResult, Processor
from app.processing.errors import (
    ProcessingInputError,
    ProcessorExecutionError,
    ProcessorTimeoutError,
    ProcessorUnavailableError,
)


_STDERR_LIMIT = 2000


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
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as exc:
            shutil.rmtree(output_directory)
            raise ProcessorUnavailableError(
                "PotreeConverter executable was not found"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(output_directory)
            raise ProcessorTimeoutError(
                "PotreeConverter exceeded its time limit"
            ) from exc
        except OSError as exc:
            shutil.rmtree(output_directory)
            raise ProcessorExecutionError(
                "PotreeConverter could not be started"
            ) from exc

        if completed.returncode != 0:
            shutil.rmtree(output_directory)
            raise ProcessorExecutionError(
                "PotreeConverter exited unsuccessfully",
                return_code=completed.returncode,
                stderr=(completed.stderr or "")[-_STDERR_LIMIT:],
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
