from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.core.errors import ErrorResponse, NotFoundError
from app.services.datasets import DatasetService

router = APIRouter(prefix="/api")

_VIEWER_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "No such viewer file"},
    410: {"model": ErrorResponse, "description": "Point cloud is no longer available"},
}


@router.get(
    "/pointcloud/{point_cloud_id}/viewer/{path:path}",
    response_class=FileResponse,
    responses=_VIEWER_ERRORS,
    include_in_schema=False,
)
async def get_viewer_file(
    point_cloud_id: str, path: str, request: Request
) -> FileResponse:
    file = request.app.state.storage.converted_file(point_cloud_id, path)
    if file is None:
        # 404 for an unknown ID, 410 when the dataset existed but its data is gone.
        DatasetService(request.app.state.storage, request.app.state.job_store).get(
            point_cloud_id
        )
        raise NotFoundError("Viewer file not found")
    return FileResponse(file)
