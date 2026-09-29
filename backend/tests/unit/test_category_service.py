import uuid
from types import SimpleNamespace

import pytest

from app.domain.errors import DomainValidationError, ResourceNotFoundError
from app.domain.services.category_service import CategoryService


class FakeCategories:
    def __init__(self) -> None:
        self.items: list[SimpleNamespace] = []

    def create(self, *, name: str, category_type: str, is_seed: bool = False):
        category = SimpleNamespace(
            id=uuid.uuid4(), name=name, type=category_type, is_seed=is_seed, status="ACTIVE"
        )
        self.items.append(category)
        return category

    def list(self, *, category_type=None, status=None):
        return [
            item
            for item in self.items
            if (category_type is None or item.type == category_type)
            and (status is None or item.status == status)
        ]

    def update(self, category_id, *, name=None, status=None):
        category = next((item for item in self.items if item.id == category_id), None)
        if category is None:
            return None
        if name is not None:
            category.name = name
        if status is not None:
            category.status = status
        return category


def test_category_lifecycle_applies_to_custom_and_seed_categories() -> None:
    store = FakeCategories()
    service = CategoryService(store)
    custom = service.create_category(name="  Mascotas  ", category_type="EXPENSE")
    seed = store.create(name="Salario", category_type="INCOME", is_seed=True)

    assert custom.name == "Mascotas"
    assert service.rename_category(custom.id, "Veterinaria").name == "Veterinaria"
    assert service.deactivate_category(custom.id).status == "INACTIVE"
    assert service.deactivate_category(seed.id).status == "INACTIVE"
    assert service.reactivate_category(custom.id).status == "ACTIVE"
    assert service.reactivate_category(seed.id).status == "ACTIVE"
    assert service.list_categories(category_type="INCOME") == [seed]


def test_category_service_rejects_invalid_input_and_missing_category() -> None:
    service = CategoryService(FakeCategories())

    with pytest.raises(DomainValidationError, match="obligatorio"):
        service.create_category(name=" ", category_type="EXPENSE")
    with pytest.raises(DomainValidationError, match="tipo"):
        service.create_category(name="Otro", category_type="OTHER")
    with pytest.raises(ResourceNotFoundError, match="no existe"):
        service.reactivate_category(uuid.uuid4())
