from typing import Any
import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings

logger = logging.getLogger("startupreach.errors")


class ErrorResponse(BaseModel):
    code: str
    message: str


def error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, message=message).model_dump(),
        headers=headers,
    )


def safe_cors_and_request_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    if request_id:
        headers["X-Request-ID"] = request_id
    origin = request.headers.get("origin")
    settings = get_settings()
    if origin and origin in settings.cors_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    return headers


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    code_by_status = {
        401: "authentication_required",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        502: "provider_error",
        503: "service_unavailable",
        429: "rate_limited",
    }
    code = code_by_status.get(exc.status_code, "request_error")
    message = str(exc.detail) if isinstance(exc.detail, str) else "Request failed."
    headers = dict(exc.headers) if exc.headers else {}
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    if request_id and "X-Request-ID" not in headers:
        headers["X-Request-ID"] = request_id
    origin = request.headers.get("origin")
    settings = get_settings()
    if origin and origin in settings.cors_origins and "Access-Control-Allow-Origin" not in headers:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    return error_response(exc.status_code, code, message, headers=headers)


async def validation_exception_handler(
    request: Request, _exc: RequestValidationError
) -> JSONResponse:
    headers = safe_cors_and_request_headers(request)
    return error_response(422, "validation_error", "Request validation failed.", headers=headers)


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    logger.error(
        "database error",
        extra={
            "request_id": request_id,
            "method": request.method,
            "route": request.url.path,
            "status_code": 503,
            "exception_type": type(exc).__name__,
        },
    )
    headers = safe_cors_and_request_headers(request)
    return error_response(
        503,
        "service_unavailable",
        "The database operation could not be completed.",
        headers=headers,
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    logger.error(
        "unhandled request exception",
        extra={
            "request_id": request_id,
            "method": request.method,
            "route": request.url.path,
            "status_code": 500,
            "exception_type": type(exc).__name__,
        },
    )
    headers = safe_cors_and_request_headers(request)
    return error_response(
        500,
        "internal_error",
        "An internal server error occurred.",
        headers=headers,
    )
