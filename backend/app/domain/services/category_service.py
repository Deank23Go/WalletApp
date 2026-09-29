from __future__ import annotations

import uuid
from typing import Any, Protocol

from app.domain.errors import DomainValidationError, ResourceNotFoundError


class CategoryStore(Protocol):
    def create(self, *, name: str, category_type: str, is_seed: bool = False) -> Any: ...
    def list(self, *, category_type: str | None = None, status: str | None = None) -> list[Any]: ...
    def update(self, category_id: uuid.UUID, *, name: str | None = None, status: str | None = None) -> Any | None: ...


class CategoryService:
    def __init__(self, categories: CategoryStore) -> None:
        self._categories = categories

    def list_categories(self, *, category_type: str | None = None, status: str | None = None) -> list[Any]:
        if category_type is not None and category_type not in {"INCOME", "EXPENSE"}:
            raise DomainValidationError("El tipo de categoría no es válido", field="type")
        if status is not None and status not in {"ACTIVE", "INACTIVE"}:
            raise DomainValidationError("El estado de la categoría no es válido", field="status")
        return self._categories.list(category_type=category_type, status=status)

    def create_category(self, *, name: str, category_type: str) -> Any:
        normalized_name = self._validate_name(name)
        if category_type not in {"INCOME", "EXPENSE"}:
            raise DomainValidationError("El tipo de categoría no es válido", field="type")
        return self._categories.create(name=normalized_name, category_type=category_type)

    def rename_category(self, category_id: uuid.UUID, name: str) -> Any:
        category = self._categories.update(category_id, name=self._validate_name(name))
        return self._require_category(category)

    def deactivate_category(self, category_id: uuid.UUID) -> Any:
        return self._set_status(category_id, "INACTIVE")

    def reactivate_category(self, category_id: uuid.UUID) -> Any:
        return self._set_status(category_id, "ACTIVE")

    def _set_status(self, category_id: uuid.UUID, status: str) -> Any:
        return self._require_category(self._categories.update(category_id, status=status))

    @staticmethod
    def _validate_name(name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise DomainValidationError("El nombre de la categoría es obligatorio", field="name")
        if len(normalized_name) > 60:
            raise DomainValidationError("El nombre de la categoría no puede exceder 60 caracteres", field="name")
        return normalized_name

    @staticmethod
    def _require_category(category: Any | None) -> Any:
        if category is None:
            raise ResourceNotFoundError("La categoría no existe", field="category_id")
        return category
