"""
app/repositories/users_repo.py
SQLAlchemy implementation of UserRepository.
Covers T2.5 — RF-01.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import User
from app.domain.ports import UserRepository


class SqlUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        email: str,
        password_hash: str,
        preferred_currency: str = "COP",
    ) -> User:
        user = User(
            email=email.lower().strip(),   # normalize at persistence boundary
            password_hash=password_hash,
            preferred_currency=preferred_currency.upper(),
        )
        self._session.add(user)
        self._session.flush()   # get id without committing
        return user

    def get_by_email(self, email: str) -> Optional[User]:
        return (
            self._session.query(User)
            .filter(User.email == email.lower().strip())
            .first()
        )

    def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return self._session.get(User, user_id)
