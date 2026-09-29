from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute


class UserScopedRepository:
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        if not isinstance(user_id, uuid.UUID):
            raise TypeError("user_id must be a UUID")
        if user_id.int == 0:
            raise ValueError("user_id must not be a nil UUID")
        self._session = session
        self._user_id = user_id

    def _tenant_filter(
        self, user_column: InstrumentedAttribute[uuid.UUID]
    ) -> ColumnElement[bool]:
        return user_column == self._user_id
