from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile, status
from pydantic import BaseModel

from app.core.errors import ErrorResponse, UnsupportedFileTypeError
from app.services.datasets import DatasetService

router = APIRouter(prefix="/api")

READ_CHUNK_BYTES = 1024 * 1024


class Bounds(BaseModel):
    minX: float
    minY: float
    minZ: float
    maxX: float
    maxY: float
    maxZ: float


class PointCloudMetadata(BaseModel):
    pointCount: int | None = None
    bounds: Bounds | None = None
    crs: str | None = None


class PointCloudResponse(BaseModel):
    id: str
    filename: str
    status: str
    metadata: PointCloudMetadata


async def _read_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(READ_CHUNK_BYTES):
        yield chunk


_UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "File exceeds the upload limit"},
    415: {"model": ErrorResponse, "description": "File extension is not .las or .laz"},
    422: {"model": ErrorResponse, "description": "Invalid request or point cloud"},
}


@router.post(
    "/upload",
    response_model=PointCloudResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_UPLOAD_ERRORS,
)
async def upload_point_cloud(
    request: Request,
    file: UploadFile = File(description="LAS/LAZ point cloud file"),
) -> PointCloudResponse:
    if not file.filename:
        raise UnsupportedFileTypeError()

    service = DatasetService(request.app.state.storage)
    stored = await service.store_upload(file.filename, _read_chunks(file))
    return PointCloudResponse(
        id=stored.id,
        filename=stored.filename,
        status=stored.status,
        metadata=PointCloudMetadata(
            pointCount=stored.metadata.point_count,
            bounds=Bounds(**asdict(stored.metadata.bounds)),
            crs=stored.metadata.crs,
        ),
    )
