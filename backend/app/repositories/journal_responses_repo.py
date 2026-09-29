from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.db.models import JournalResponse
from app.domain.ports import JournalResponseRepository, JsonObject, StoredResponse
from app.repositories.base import UserScopedRepository


class SqlJournalResponseRepository(UserScopedRepository, JournalResponseRepository):
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        super().__init__(session, user_id)

    def claim(self, idempotency_key: uuid.UUID) -> bool:
        statement = (
            insert(JournalResponse)
            .values(user_id=self._user_id, idempotency_key=idempotency_key, state="PENDING")
            .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
            .returning(JournalResponse.idempotency_key)
        )
        return self._session.scalar(statement) is not None

    def complete(self, idempotency_key: uuid.UUID, *, status_code: int, body: JsonObject) -> bool:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(JournalResponse)
                .where(
                    self._tenant_filter(JournalResponse.user_id),
                    JournalResponse.idempotency_key == idempotency_key,
                    JournalResponse.state == "PENDING",
                )
                .values(state="COMPLETED", status_code=status_code, body=body)
            ),
        )
        return result.rowcount == 1

    def load(self, idempotency_key: uuid.UUID) -> StoredResponse | None:
        record = self._session.scalar(
            select(JournalResponse).where(
                self._tenant_filter(JournalResponse.user_id),
                JournalResponse.idempotency_key == idempotency_key,
                JournalResponse.state == "COMPLETED",
            )
        )
        if record is None or record.status_code is None or record.body is None:
            return None
        return StoredResponse(status_code=record.status_code, body=record.body)
