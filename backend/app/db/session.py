from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from types import TracebackType

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_db_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


_settings = Settings()  # type: ignore[call-arg]
engine = create_db_engine(_settings.database_url)
SessionLocal = create_session_factory(engine)


class SqlAlchemyUnitOfWork:
    def __init__(self, factory: sessionmaker[Session] = SessionLocal) -> None:
        self.session = factory()
        self._completed = False

    def commit(self) -> None:
        self.session.commit()
        self._completed = True

    def rollback(self) -> None:
        self.session.rollback()
        self._completed = True

    def close(self) -> None:
        if not self._completed and self.session.in_transaction():
            self.session.rollback()
        self.session.close()

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exception_type is not None:
            self.rollback()
        self.close()


@contextmanager
def transactional_session(
    factory: sessionmaker[Session] = SessionLocal,
) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
