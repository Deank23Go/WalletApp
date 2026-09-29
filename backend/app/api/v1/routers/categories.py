from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUserDep, IdempotencyKeyDep, UnitOfWorkDep
from app.core.idempotency import IdempotencyCoordinator
from app.domain.ports import JsonObject
from app.domain.services.category_service import CategoryService
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.journal_responses_repo import SqlJournalResponseRepository
from app.schemas.categories import CategoryCreateRequest, CategoryResponse, CategoryType, CategoryUpdateRequest

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    current_user: CurrentUserDep,
    uow: UnitOfWorkDep,
    category_type: Annotated[CategoryType | None, Query(alias="type")] = None,
) -> list[CategoryResponse]:
    categories = CategoryService(SqlCategoryRepository(uow.session, current_user.id)).list_categories(
        category_type=category_type
    )
    return [CategoryResponse.model_validate(category) for category in categories]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreateRequest,
    current_user: CurrentUserDep,
    idempotency_key: IdempotencyKeyDep,
    uow: UnitOfWorkDep,
) -> CategoryResponse:
    responses = SqlJournalResponseRepository(uow.session, current_user.id)
    coordinator = IdempotencyCoordinator(responses, operation="category.create")
    replay = coordinator.claim_or_replay(idempotency_key)
    if replay is not None:
        return CategoryResponse.model_validate(replay.body)
    category = CategoryService(SqlCategoryRepository(uow.session, current_user.id)).create_category(
        name=payload.name,
        category_type=payload.type,
    )
    result = CategoryResponse.model_validate(category)
    coordinator.complete(
        idempotency_key,
        status_code=201,
        response=cast(JsonObject, result.model_dump(mode="json")),
    )
    uow.commit()
    return result


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdateRequest,
    current_user: CurrentUserDep,
    uow: UnitOfWorkDep,
) -> CategoryResponse:
    service = CategoryService(SqlCategoryRepository(uow.session, current_user.id))
    if payload.name is not None:
        category = service.rename_category(category_id, payload.name)
    elif payload.status == "ACTIVE":
        category = service.reactivate_category(category_id)
    else:
        category = service.deactivate_category(category_id)
    uow.commit()
    return CategoryResponse.model_validate(category)
