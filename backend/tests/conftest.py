from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.test.yml"
EXTERNAL_TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://walletapp:walletapp@localhost:55432/walletapp_test"
TEST_DATABASE_URL = EXTERNAL_TEST_DATABASE_URL or DEFAULT_TEST_DATABASE_URL

if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must reference a database ending in _test")

os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "integration-test-secret-with-at-least-32-bytes")

from app.api.v1.deps import get_uow, rate_limiter
from app.db.models import Account, Category, User
from app.db.session import SqlAlchemyUnitOfWork
from app.main import app
from app.repositories.accounts_repo import SqlAccountRepository
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.users_repo import SqlUserRepository

TABLES = (
    "journal_responses, refresh_tokens, journal_lines, journals, "
    "categories, accounts, users"
)


def _run_alembic(*arguments: str, database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=os.environ | {"DATABASE_URL": database_url},
        check=True,
        capture_output=True,
        text=True,
    )


def _wait_for_database(database_url: str, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            engine = create_engine(database_url)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            engine.dispose()
            return
        except Exception as error:
            last_error = error
            time.sleep(0.2)
    raise RuntimeError("PostgreSQL test database did not become ready") from last_error


@pytest.fixture(scope="session")
def postgres_service() -> Iterator[str]:
    if EXTERNAL_TEST_DATABASE_URL is not None:
        _wait_for_database(TEST_DATABASE_URL)
        yield TEST_DATABASE_URL
        return

    environment = os.environ | {"TEST_POSTGRES_PORT": "55432"}
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "walletapp-tests",
            "-f",
            str(COMPOSE_FILE),
            "up",
            "-d",
            "--wait",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )
    try:
        _wait_for_database(TEST_DATABASE_URL)
        yield TEST_DATABASE_URL
    finally:
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                "walletapp-tests",
                "-f",
                str(COMPOSE_FILE),
                "down",
                "-v",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
        )


@pytest.fixture(scope="session")
def test_database_url(postgres_service: str) -> str:
    return postgres_service


@pytest.fixture(scope="session")
def db_engine(test_database_url: str) -> Iterator[Engine]:
    _run_alembic("downgrade", "base", database_url=test_database_url)
    _run_alembic("upgrade", "head", database_url=test_database_url)
    engine = create_engine(test_database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    with db_engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(bind=connection, expire_on_commit=False)
        session = factory()
        yield session
        session.close()
        if transaction.is_active:
            transaction.rollback()


@pytest.fixture
def committed_session_factory(db_engine: Engine) -> sessionmaker[Session]:
    with db_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def api_client(committed_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_uow() -> Iterator[SqlAlchemyUnitOfWork]:
        uow = SqlAlchemyUnitOfWork(committed_session_factory)
        try:
            yield uow
            uow.commit()
        except Exception:
            uow.rollback()
            raise
        finally:
            uow.close()

    app.dependency_overrides[get_uow] = override_get_uow
    rate_limiter.clear()
    with TestClient(app, base_url="https://testserver") as client:
        yield client
    rate_limiter.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def user(db_session: Session) -> User:
    return SqlUserRepository(db_session).create(
        email=f"user-{uuid.uuid4()}@example.com",
        password_hash="hash",
    )


@pytest.fixture
def account(db_session: Session, user: User) -> Account:
    return SqlAccountRepository(db_session, user.id).create(name="Cash", account_type="CASH")


@pytest.fixture
def categories(db_session: Session, user: User) -> tuple[Category, Category]:
    repository = SqlCategoryRepository(db_session, user.id)
    return (
        repository.create(name="Salary", category_type="INCOME"),
        repository.create(name="Market", category_type="EXPENSE"),
    )


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


@pytest.fixture
def e2e_client(
    committed_session_factory: sessionmaker[Session],
    test_database_url: str,
) -> Iterator[httpx.Client]:
    port = _free_port()
    environment = os.environ | {
        "DATABASE_URL": test_database_url,
        "JWT_SECRET": "e2e-test-secret-with-at-least-32-bytes",
        "REFRESH_COOKIE_SECURE": "false",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout is not None else ""
                raise RuntimeError(f"Uvicorn stopped during startup:\n{output}")
            try:
                response = httpx.get(f"{base_url}/health", timeout=0.5)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Uvicorn did not become ready")
        with httpx.Client(base_url=base_url, timeout=10) as client:
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
