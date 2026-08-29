"""
Unified error handling for the application.
Defines custom exceptions and a standard error response model.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base application exception with a structured payload."""

    def __init__(
        self,
        code: str = "INTERNAL_ERROR",
        message: str = "An unexpected error occurred.",
        status_code: int = 500,
        details: dict | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found.", details: dict | None = None):
        super().__init__(code="NOT_FOUND", message=message, status_code=404, details=details)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation failed.", details: dict | None = None):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422, details=details)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "unavailable")


def _error_response(code: str, message: str, request_id: str, details: dict | None = None) -> JSONResponse:
    body = {
        "code": code,
        "message": message,
        "request_id": request_id,
        "details": details or {},
    }
    return JSONResponse(status_code=500, content=body)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": _request_id(request),
            "details": exc.details,
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": f"HTTP_{exc.status_code}",
            "message": exc.detail,
            "request_id": _request_id(request),
            "details": {},
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "request_id": _request_id(request),
            "details": {"errors": exc.errors()},
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred.",
            "request_id": _request_id(request),
            "details": {},
        },
    )


def register_error_handlers(app):
    """Register all error handlers on the FastAPI application."""
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
