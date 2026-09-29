from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.deps import RateLimitExceeded
from app.domain.errors import (
    AuthenticationError,
    DomainConflictError,
    DomainError,
    DomainValidationError,
    ResourceNotFoundError,
)

logger = logging.getLogger(__name__)


def error_response(*, status_code: int, field: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": [{"field": field, "message": message}]},
    )


def validation_message(error: dict[str, Any]) -> str:
    context = error.get("ctx") or {}
    nested_error = context.get("error")
    if nested_error is not None:
        return str(nested_error)
    error_type = error.get("type", "")
    translations = {
        "missing": "El campo es obligatorio",
        "string_too_short": "El valor es demasiado corto",
        "string_too_long": "El valor excede la longitud permitida",
        "literal_error": "El valor no es válido",
        "uuid_parsing": "El identificador no tiene un formato válido",
        "date_from_datetime_parsing": "La fecha no tiene un formato válido",
        "greater_than_equal": "El valor está por debajo del mínimo permitido",
        "less_than_equal": "El valor excede el máximo permitido",
    }
    return translations.get(error_type, "El valor enviado no es válido")


def domain_status(error: DomainError) -> int:
    if isinstance(error, AuthenticationError):
        return 401
    if isinstance(error, ResourceNotFoundError):
        return 404
    if isinstance(error, DomainConflictError):
        return 409
    if isinstance(error, DomainValidationError):
        return 422
    return 400


def integrity_message(error: IntegrityError) -> tuple[str, str, int]:
    constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint_name == "uq_users_email":
        return "email", "Este correo ya está registrado", 409
    if constraint_name == "uq_accounts_user_name":
        return "name", "Ya existe una cuenta con este nombre", 409
    if constraint_name == "uq_categories_user_name_type":
        return "name", "Ya existe una categoría con este nombre y tipo", 422
    if constraint_name in {"uq_journals_user_idempotency", "journal_responses_pkey"}:
        return "Idempotency-Key", "La clave de idempotencia ya fue utilizada", 409
    return "general", "La operación entra en conflicto con datos existentes", 409


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
        details = []
        for item in error.errors():
            location = item.get("loc", ())
            field = str(location[-1]) if location else "general"
            details.append({"field": field, "message": validation_message(item)})
        return JSONResponse(status_code=422, content={"detail": details})

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, error: DomainError) -> JSONResponse:
        return error_response(status_code=domain_status(error), field=error.field, message=error.message)

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_request: Request, error: IntegrityError) -> JSONResponse:
        field, message, status_code = integrity_message(error)
        return error_response(status_code=status_code, field=field, message=message)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_request: Request, error: RateLimitExceeded) -> JSONResponse:
        return error_response(status_code=429, field="general", message=str(error))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled application error", exc_info=error)
        return error_response(
            status_code=500,
            field="general",
            message="Ocurrió un error inesperado. Intente nuevamente",
        )
