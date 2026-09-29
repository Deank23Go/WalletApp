from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.v1.routers import accounts, auth, balance, categories, movements


def create_app() -> FastAPI:
    application = FastAPI(title="WalletApp API", version="1.0.0")
    install_error_handlers(application)
    application.include_router(auth.router, prefix="/api/v1")
    application.include_router(accounts.router, prefix="/api/v1")
    application.include_router(categories.router, prefix="/api/v1")
    application.include_router(movements.router, prefix="/api/v1")
    application.include_router(balance.router, prefix="/api/v1")

    @application.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
