from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, File, Request, UploadFile, status
from pydantic import BaseModel

from app.core.errors import ErrorResponse, UnsupportedFileTypeError
from app.services.datasets import DatasetService
from app.services.las_metadata import LasMetadata

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


PointCloudStatus = Literal["uploaded", "converting", "ready", "failed"]


class PointCloudResponse(BaseModel):
    id: str
    filename: str
    status: PointCloudStatus
    metadata: PointCloudMetadata


class PointCloudDetailResponse(PointCloudResponse):
    viewerUrl: str | None = None
    sourceId: str | None = None


def _metadata_response(metadata: LasMetadata) -> PointCloudMetadata:
    return PointCloudMetadata(
        pointCount=metadata.point_count,
        bounds=Bounds(**asdict(metadata.bounds)),
        crs=metadata.crs,
    )


def _service(request: Request) -> DatasetService:
    return DatasetService(request.app.state.storage, request.app.state.job_store)


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

    service = _service(request)
    stored = await service.store_upload(file.filename, _read_chunks(file))
    return PointCloudResponse(
        id=stored.id,
        filename=stored.filename,
        status=stored.status,
        metadata=_metadata_response(stored.metadata),
    )


_POINT_CLOUD_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Point cloud not found"},
}


@router.get(
    "/pointcloud/{point_cloud_id}",
    response_model=PointCloudDetailResponse,
    responses=_POINT_CLOUD_ERRORS,
)
async def get_point_cloud(
    point_cloud_id: str, request: Request
) -> PointCloudDetailResponse:
    found = _service(request).get(point_cloud_id)
    return PointCloudDetailResponse(
        id=found.id,
        filename=found.filename,
        status=found.status,
        metadata=_metadata_response(found.metadata),
        viewerUrl=(
            f"/api/pointcloud/{found.id}/viewer/metadata.json"
            if found.status == "ready"
            else None
        ),
        sourceId=None,
    )
