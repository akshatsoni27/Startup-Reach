from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.errors import (
    error_response,
    http_exception_handler,
    sqlalchemy_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.v1 import router as v1_router
from app.config import get_settings
from app.observability import RequestContextMiddleware, configure_logging
from app.rate_limit import check_rate_limit

settings = get_settings()
configure_logging()


class HealthResponse(BaseModel):
    status: str
    application: str
    version: str


app = FastAPI(
    title=settings.application_name,
    description="Global startup discovery and founder outreach assistant",
    version=settings.application_version,
)


async def provider_rate_limit(request: Request, call_next):
    try:
        check_rate_limit(request)
    except HTTPException:
        return error_response(429, "rate_limited", "Rate limit exceeded. Please retry later.")
    return await call_next(request)


# Inner user middleware: rate limit enforcement
app.add_middleware(BaseHTTPMiddleware, dispatch=provider_rate_limit)

# Request context and observability middleware
app.add_middleware(RequestContextMiddleware)

# Outermost user middleware: CORS (evaluates first on requests, wraps all user responses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(v1_router)


@app.get("/api/v1/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        application=settings.application_name,
        version=settings.application_version,
    )
