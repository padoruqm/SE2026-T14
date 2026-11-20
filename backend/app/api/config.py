from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from app.core.errors import ErrorResponse, ForbiddenError, UnauthorizedError

router = APIRouter(prefix="/api")

MIN_UPLOAD_LIMIT_BYTES = 1
MAX_UPLOAD_LIMIT_BYTES = 1024 * 1024 * 1024  # 1 GiB


class AppConfigResponse(BaseModel):
    maxUploadBytes: int


class AppConfigUpdate(BaseModel):
    maxUploadBytes: int = Field(
        ge=MIN_UPLOAD_LIMIT_BYTES, le=MAX_UPLOAD_LIMIT_BYTES, strict=True
    )


_ADMIN_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Admin token is missing"},
    403: {"model": ErrorResponse, "description": "Admin token is not valid"},
    422: {"model": ErrorResponse, "description": "Value is outside the allowed range"},
}


def require_admin(
    request: Request, x_admin_token: str | None = Header(default=None)
) -> None:
    if not x_admin_token:
        raise UnauthorizedError()
    expected = request.app.state.admin_token
    # No configured token means the admin endpoint stays closed.
    if expected is None or not hmac.compare_digest(x_admin_token, expected):
        raise ForbiddenError()


@router.get("/config", response_model=AppConfigResponse)
async def get_config(request: Request) -> AppConfigResponse:
    return AppConfigResponse(maxUploadBytes=request.app.state.storage.max_upload_bytes)


@router.put(
    "/admin/config",
    response_model=AppConfigResponse,
    responses=_ADMIN_ERRORS,
    dependencies=[Depends(require_admin)],
)
async def update_config(body: AppConfigUpdate, request: Request) -> AppConfigResponse:
    request.app.state.storage.max_upload_bytes = body.maxUploadBytes
    return AppConfigResponse(maxUploadBytes=body.maxUploadBytes)
