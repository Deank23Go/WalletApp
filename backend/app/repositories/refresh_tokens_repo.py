from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.db.models import RefreshToken
from app.domain.ports import RefreshTokenRepository


class SqlRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        family_id: uuid.UUID,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
        )
        self._session.add(token)
        self._session.flush()
        return token

    def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        return self._session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )

    def revoke(self, token_hash: str, *, revoked_at: datetime) -> bool:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=revoked_at)
            ),
        )
        return result.rowcount == 1

    def revoke_family(self, family_id: uuid.UUID, *, revoked_at: datetime) -> int:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=revoked_at)
            ),
        )
        return result.rowcount
