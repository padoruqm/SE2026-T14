from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProcessingContext:
    input_path: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    output_directory: Path
    metadata_path: Path


@runtime_checkable
class Processor(Protocol):
    key: str
    input_schema: Mapping[str, object]

    def execute(
        self, context: ProcessingContext, parameters: Mapping[str, object]
    ) -> ProcessingResult: ...
