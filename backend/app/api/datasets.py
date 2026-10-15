from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.storage.local import UploadTooLargeError


router = APIRouter(prefix="/api/v1")


class DatasetUploadResponse(BaseModel):
    id: str
    original_filename: str
    size_bytes: int
    status: str


@router.post(
    "/datasets",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_dataset(
    request: Request,
    x_filename: str = Header(
        ...,
        description="Original LAS/LAZ filename; request body contains the raw file bytes.",
    ),
) -> DatasetUploadResponse:
    safe_filename = Path(x_filename).name
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in {".las", ".laz"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .las and .laz files are supported.",
        )

    dataset_id = str(uuid4())
    try:
        _, size_bytes = await request.app.state.storage.save(
            dataset_id,
            suffix,
            request.stream(),
        )
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The uploaded file exceeds APP_MAX_UPLOAD_BYTES.",
        ) from exc

    return DatasetUploadResponse(
        id=dataset_id,
        original_filename=safe_filename,
        size_bytes=size_bytes,
        status="uploaded",
    )
