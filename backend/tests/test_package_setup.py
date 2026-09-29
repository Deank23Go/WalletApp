from importlib import import_module
from importlib.metadata import requires

from packaging.requirements import Requirement

REQUIRED_MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
    "pydantic": "pydantic",
    "pydantic-settings": "pydantic_settings",
    "argon2-cffi": "argon2",
    "PyJWT": "jwt",
    "pytest": "pytest",
    "pytest-cov": "pytest_cov",
    "httpx": "httpx",
}


def test_walletapp_backend_declares_required_dependencies() -> None:
    declared = requires("walletapp-backend") or []
    normalized = {Requirement(requirement).name.lower() for requirement in declared}

    assert {name.lower() for name in REQUIRED_MODULES} <= normalized


def test_required_modules_are_importable() -> None:
    for module_name in REQUIRED_MODULES.values():
        import_module(module_name)


def test_app_package_is_importable() -> None:
    import_module("app")
