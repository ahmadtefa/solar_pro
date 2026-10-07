"""Typed application errors and FastAPI exception handlers.

Every error returned by the API has a stable machine readable ``code`` so the
Flutter client can translate messages without string matching.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base class for all expected application errors."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str = "Request could not be processed", **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationFailure(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class BusinessRuleError(AppError):
    """Domain rule violation (e.g. posting an unbalanced journal entry)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "business_rule_violation"


class TenantError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "tenant_violation"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class AccountLockedError(AppError):
    status_code = status.HTTP_423_LOCKED
    code = "account_locked"


class NotSupportedError(AppError):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = "not_supported"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "validation_error",
                "message": "Request payload failed validation",
                "details": {"errors": _jsonable_errors(exc.errors())},
            },
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "integrity_error",
                "message": "The operation violates a database constraint",
                "details": {"error": _clean_db_error(str(exc.orig))},
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "database_error", "message": "A database error occurred", "details": {}},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": f"http_{exc.status_code}", "message": str(exc.detail), "details": {}},
            headers=getattr(exc, "headers", None),
        )


def _clean_db_error(raw: str) -> str:
    """Strip driver specific noise but keep the useful constraint detail."""
    first_line = raw.splitlines()[0] if raw else ""
    return first_line[:400]


def _jsonable_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for error in errors:
        cleaned.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return cleaned
