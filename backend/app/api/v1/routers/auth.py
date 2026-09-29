from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.api.v1.deps import (
    CurrentUserDep,
    UnitOfWorkDep,
    enforce_login_rate_limit,
    enforce_register_rate_limit,
    settings,
)
from app.core.security import Argon2PasswordHasher, JwtAccessTokenCodec, OpaqueRefreshTokenCodec, SystemClock
from app.domain.errors import RefreshTokenReuseError
from app.domain.services.auth_service import AuthService, SessionResult
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.refresh_tokens_repo import SqlRefreshTokenRepository
from app.repositories.users_repo import SqlUserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, SessionResponse, UserResponse

router = APIRouter(tags=["auth"])
clock = SystemClock()


def _auth_service(uow: UnitOfWorkDep) -> AuthService:
    return AuthService(
        users=SqlUserRepository(uow.session),
        refresh_tokens=SqlRefreshTokenRepository(uow.session),
        seed_categories=lambda user_id: SqlCategoryRepository(uow.session, user_id),
        password_hasher=Argon2PasswordHasher(),
        access_tokens=JwtAccessTokenCodec(
            secret=settings.jwt_secret.get_secret_value(),
            issuer=settings.jwt_issuer,
            ttl_seconds=settings.jwt_ttl_seconds,
            clock=clock,
        ),
        refresh_codec=OpaqueRefreshTokenCodec(),
        clock=clock,
        refresh_ttl_seconds=settings.refresh_ttl_seconds,
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_ttl_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path=settings.refresh_cookie_path,
    )


def _session_response(result: SessionResult) -> SessionResponse:
    return SessionResponse(
        access_token=result.access_token.value,
        expires_in=result.access_token.expires_in,
        user=UserResponse.model_validate(result.user),
    )


@router.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
def register(payload: RegisterRequest, uow: UnitOfWorkDep) -> UserResponse:
    user = _auth_service(uow).register(email=payload.email, password=payload.password)
    uow.commit()
    return UserResponse.model_validate(user)


@router.post(
    "/auth/login",
    response_model=SessionResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(payload: LoginRequest, response: Response, uow: UnitOfWorkDep) -> SessionResponse:
    result = _auth_service(uow).login(email=payload.email, password=payload.password)
    uow.commit()
    _set_refresh_cookie(response, result.refresh_token)
    return _session_response(result)


@router.post("/auth/refresh", response_model=SessionResponse)
def refresh_session(
    response: Response,
    uow: UnitOfWorkDep,
    refresh_token: Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)] = None,
) -> SessionResponse:
    if refresh_token is None:
        from app.domain.errors import AuthenticationError

        raise AuthenticationError("La sesión no es válida")
    try:
        result = _auth_service(uow).refresh(refresh_token)
    except RefreshTokenReuseError:
        uow.commit()
        raise
    uow.commit()
    _set_refresh_cookie(response, result.refresh_token)
    return _session_response(result)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    uow: UnitOfWorkDep,
    refresh_token: Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)] = None,
) -> None:
    _auth_service(uow).logout(refresh_token)
    uow.commit()
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.get("/users/me", response_model=UserResponse)
def get_me(current_user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(current_user)
