from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict

from app.core.errors import ErrorResponse, NotFoundError
from app.jobs.store import Job, JobState

router = APIRouter(prefix="/api")


class ConvertRequest(BaseModel):
    force: bool = False


class CropBounds(BaseModel):
    # Strict: booleans and numeric strings are not numbers, and NaN/Infinity
    # (which Python's JSON parser accepts) are rejected.
    model_config = ConfigDict(strict=True, allow_inf_nan=False, extra="forbid")

    minX: float
    minY: float
    minZ: float
    maxX: float
    maxY: float
    maxZ: float


class CropRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bounds: CropBounds
    outputFormat: Literal["las", "laz"] = "laz"


class JobErrorResponse(BaseModel):
    code: str
    message: str


class JobResponse(BaseModel):
    id: str
    type: str
    state: JobState
    progress: int | None
    resultId: str | None
    error: JobErrorResponse | None

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
            type=job.type,
            state=job.state,
            progress=job.progress,
            resultId=job.result_id,
            error=(
                JobErrorResponse(code=job.error.code, message=job.error.message)
                if job.error
                else None
            ),
        )


_CONVERT_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Point cloud not found"},
    409: {"model": ErrorResponse, "description": "Already converted or converting"},
}
_CROP_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Point cloud not found"},
    409: {"model": ErrorResponse, "description": "Point cloud has no file to crop"},
    410: {"model": ErrorResponse, "description": "Point cloud is no longer available"},
    422: {"model": ErrorResponse, "description": "Invalid bounds or output format"},
}
_JOB_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Job not found"},
}


@router.post(
    "/pointcloud/{point_cloud_id}/convert",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_CONVERT_ERRORS,
)
async def convert_point_cloud(
    point_cloud_id: str,
    request: Request,
    body: ConvertRequest | None = None,
) -> JobResponse:
    job = request.app.state.jobs.start(point_cloud_id, force=body.force if body else False)
    return JobResponse.from_job(job)


@router.post(
    "/pointcloud/{point_cloud_id}/crop",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_CROP_ERRORS,
)
async def crop_point_cloud(
    point_cloud_id: str, body: CropRequest, request: Request
) -> JobResponse:
    job = request.app.state.crops.start(
        point_cloud_id, body.bounds.model_dump(), body.outputFormat
    )
    return JobResponse.from_job(job)


@router.get("/job/{job_id}", response_model=JobResponse, responses=_JOB_ERRORS)
async def get_job(job_id: str, request: Request) -> JobResponse:
    job = request.app.state.job_store.get(job_id)
    if job is None:
        raise NotFoundError("Job not found")
    return JobResponse.from_job(job)
