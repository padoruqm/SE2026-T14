from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.core.errors import AppError, ConflictError, ErrorResponse, NotFoundError
from app.storage.viewer_drafts import DraftConflict

router = APIRouter(prefix="/api/pointcloud", tags=["drafts"])


class ViewerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pointSize: Annotated[float, Field(strict=True, ge=1, le=5, multiple_of=0.5)]
    colorMode: Literal["rgb", "elevation", "intensity"]


class SaveViewerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedRevision: Annotated[StrictInt, Field(ge=0)]
    operationId: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    state: ViewerState


class ViewerDraft(BaseModel):
    revision: int
    state: ViewerState


class DraftStorageUnavailable(AppError):
    status_code = 503
    message = "Draft storage is unavailable; your changes have not been acknowledged"


_ERRORS = {
    404: {"model": ErrorResponse, "description": "Dataset not found"},
    503: {"model": ErrorResponse, "description": "Draft storage unavailable"},
}


def _require_dataset(request: Request, dataset_id: str) -> None:
    if request.app.state.storage.find(dataset_id) is None:
        raise NotFoundError("Point cloud not found")


@router.get("/{dataset_id}/draft", response_model=ViewerDraft, responses=_ERRORS)
def get_viewer_draft(dataset_id: str, request: Request) -> dict:
    _require_dataset(request, dataset_id)
    try:
        return request.app.state.viewer_drafts.load(dataset_id)
    except sqlite3.Error as exc:
        raise DraftStorageUnavailable() from exc


@router.put(
    "/{dataset_id}/draft",
    response_model=ViewerDraft,
    responses={**_ERRORS, 409: {"model": ErrorResponse, "description": "Stale or reused command"}},
)
def save_viewer_draft(dataset_id: str, body: SaveViewerDraft, request: Request) -> dict:
    _require_dataset(request, dataset_id)
    try:
        return request.app.state.viewer_drafts.save(
            dataset_id, body.expectedRevision, body.operationId, body.state.model_dump()
        )
    except DraftConflict as exc:
        raise ConflictError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise DraftStorageUnavailable() from exc
