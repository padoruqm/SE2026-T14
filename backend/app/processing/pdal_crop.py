from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from app.core.errors import InvalidPointCloudError
from app.processing.base import ProcessingContext, ProcessingResult, Processor
from app.processing.errors import (
    ProcessingInputError,
    ProcessorExecutionError,
    ProcessorTimeoutError,
    ProcessorUnavailableError,
)
from app.services.las_metadata import (
    HEADER_PROBE_BYTES,
    LasMetadata,
    parse_las_metadata,
    required_head_length,
)

_BOUNDS_KEYS = ("minX", "minY", "minZ", "maxX", "maxY", "maxZ")
_SUPPORTED_FORMATS = frozenset({"las", "laz"})
_OUTPUT_LIMIT = 2000


def _read_metadata(path: Path) -> LasMetadata:
    with path.open("rb") as source:
        head = source.read(HEADER_PROBE_BYTES)
        required = required_head_length(head)
        head += source.read(required - len(head))
    return parse_las_metadata(head)


def _tail(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return (value or "")[-_OUTPUT_LIMIT:]


class PdalCropProcessor(Processor):
    key = "pdal-crop"
    input_schema: Mapping[str, object] = {
        "type": "object",
        "properties": {
            "bounds": {
                "type": "object",
                "properties": {
                    key: {"type": "number"} for key in _BOUNDS_KEYS
                },
                "required": list(_BOUNDS_KEYS),
                "additionalProperties": False,
            },
            "output_format": {"type": "string", "enum": ["las", "laz"]},
        },
        "required": ["bounds", "output_format"],
        "additionalProperties": False,
    }

    def __init__(
        self, executable: str | None = None, timeout_seconds: float = 300
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self._executable = executable or os.getenv("APP_PDAL_PATH", "pdal")
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _parameters(parameters: Mapping[str, object]) -> tuple[dict[str, float], str]:
        if set(parameters) != {"bounds", "output_format"}:
            raise ProcessingInputError("Crop requires bounds and an output format")

        raw_bounds = parameters["bounds"]
        if not isinstance(raw_bounds, Mapping) or set(raw_bounds) != set(
            _BOUNDS_KEYS
        ):
            raise ProcessingInputError("Crop bounds must define all six coordinates")

        bounds: dict[str, float] = {}
        for key in _BOUNDS_KEYS:
            value = raw_bounds[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProcessingInputError("Crop bounds must be finite numbers")
            try:
                coordinate = float(value)
            except OverflowError as exc:
                raise ProcessingInputError(
                    "Crop bounds must be finite numbers"
                ) from exc
            if not math.isfinite(coordinate):
                raise ProcessingInputError("Crop bounds must be finite numbers")
            bounds[key] = coordinate

        if any(bounds[f"min{axis}"] > bounds[f"max{axis}"] for axis in "XYZ"):
            raise ProcessingInputError("Crop minimum bounds must not exceed maxima")

        output_format = parameters["output_format"]
        if (
            not isinstance(output_format, str)
            or output_format not in _SUPPORTED_FORMATS
        ):
            raise ProcessingInputError("Crop output format must be las or laz")
        return bounds, output_format

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult:
        bounds, output_format = self._parameters(parameters)
        input_path = context.input_path.resolve()
        if input_path.suffix.lower() not in {".las", ".laz"}:
            raise ProcessingInputError("PDAL crop accepts LAS and LAZ files only")
        if not input_path.is_file():
            raise ProcessingInputError("The input point cloud does not exist")

        output_directory = context.output_directory.resolve()
        output_path = output_directory / f"cropped.{output_format}"
        metadata_path = output_directory / "metadata.json"
        try:
            output_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ProcessingInputError(
                "The output directory must not already exist"
            ) from exc

        crop_stage: dict[str, object] = {
            "type": "filters.crop",
            "bounds": {
                "minx": bounds["minX"],
                "miny": bounds["minY"],
                "minz": bounds["minZ"],
                "maxx": bounds["maxX"],
                "maxy": bounds["maxY"],
                "maxz": bounds["maxZ"],
            },
        }
        writer_stage: dict[str, object] = {
            "type": "writers.las",
            "filename": str(output_path),
            "forward": "all",
        }
        if output_format == "laz":
            writer_stage["compression"] = True

        pipeline = [
            {"type": "readers.las", "filename": str(input_path)},
            crop_stage,
            writer_stage,
        ]
        command = [self._executable, "pipeline", "--stdin"]
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(pipeline),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            shutil.rmtree(output_directory, ignore_errors=True)
            raise ProcessorUnavailableError("PDAL executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(output_directory, ignore_errors=True)
            raise ProcessorTimeoutError(
                "PDAL crop exceeded its time limit"
            ) from exc
        except OSError as exc:
            shutil.rmtree(output_directory, ignore_errors=True)
            raise ProcessorExecutionError("PDAL could not be started") from exc

        output = _tail(completed.stdout)
        if completed.returncode != 0:
            shutil.rmtree(output_directory, ignore_errors=True)
            raise ProcessorExecutionError(
                "PDAL crop exited unsuccessfully",
                return_code=completed.returncode,
                stderr=output,
            )

        if output_path.is_symlink() or not output_path.is_file():
            shutil.rmtree(output_directory, ignore_errors=True)
            raise ProcessorExecutionError(
                "PDAL completed without producing a cropped point cloud",
                stderr=output,
            )

        try:
            metadata = _read_metadata(output_path)
            metadata_path.write_text(
                json.dumps(
                    {
                        "point_count": metadata.point_count,
                        "bounds": asdict(metadata.bounds),
                        "crs": metadata.crs,
                    }
                ),
                encoding="utf-8",
            )
        except (InvalidPointCloudError, OSError, struct.error) as exc:
            shutil.rmtree(output_directory, ignore_errors=True)
            raise ProcessorExecutionError(
                "PDAL produced an unreadable cropped point cloud",
                stderr=output,
            ) from exc

        return ProcessingResult(
            output_directory=output_directory,
            metadata_path=metadata_path,
        )
