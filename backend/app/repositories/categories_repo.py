from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category
from app.domain.ports import CategoryRepository
from app.domain.seed_catalog import SEED_CATALOG
from app.repositories.base import UserScopedRepository


class SqlCategoryRepository(UserScopedRepository, CategoryRepository):
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        super().__init__(session, user_id)

    def create(self, *, name: str, category_type: str, is_seed: bool = False) -> Category:
        category = Category(user_id=self._user_id, name=name.strip(), type=category_type, is_seed=is_seed)
        self._session.add(category)
        self._session.flush()
        return category

    def list(self, *, category_type: str | None = None, status: str | None = None) -> list[Category]:
        statement = select(Category).where(self._tenant_filter(Category.user_id))
        if category_type is not None:
            statement = statement.where(Category.type == category_type)
        if status is not None:
            statement = statement.where(Category.status == status)
        return list(self._session.scalars(statement.order_by(Category.created_at)))

    def get_by_id(self, category_id: uuid.UUID) -> Category | None:
        return self._session.scalar(select(Category).where(Category.id == category_id, self._tenant_filter(Category.user_id)))

    def update(self, category_id: uuid.UUID, *, name: str | None = None, status: str | None = None) -> Category | None:
        category = self.get_by_id(category_id)
        if category is None:
            return None
        if name is not None:
            category.name = name.strip()
        if status is not None:
            category.status = status
        self._session.flush()
        return category

    def clone_seed_catalog(self) -> int:
        rows = [Category(user_id=self._user_id, name=item["name"], type=item["type"], is_seed=True) for item in SEED_CATALOG]
        self._session.add_all(rows)
        self._session.flush()
        return len(rows)
