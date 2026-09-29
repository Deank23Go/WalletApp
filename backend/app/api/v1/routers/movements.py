from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, cast

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUserDep, IdempotencyKeyDep, UnitOfWorkDep
from app.core.security import SystemClock
from app.db.models import Journal
from app.domain.errors import DomainValidationError
from app.domain.services.movement_service import MovementService
from app.domain.services.void_service import VoidService
from app.repositories.accounts_repo import SqlAccountRepository
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.journal_responses_repo import SqlJournalResponseRepository
from app.repositories.journals_repo import SqlJournalRepository
from app.schemas.movements import (
    MovementCreateRequest,
    MovementCreateResponse,
    MovementHistoryItem,
    MovementHistoryResponse,
    ResourceSummary,
    VoidMovementResponse,
    VoidMovementSummary,
)

router = APIRouter(prefix="/movements", tags=["movements"])
clock = SystemClock()


@router.post("", response_model=MovementCreateResponse, status_code=status.HTTP_201_CREATED)
def create_movement(
    payload: MovementCreateRequest,
    current_user: CurrentUserDep,
    idempotency_key: IdempotencyKeyDep,
    uow: UnitOfWorkDep,
) -> MovementCreateResponse:
    result = MovementService(
        SqlAccountRepository(uow.session, current_user.id),
        SqlCategoryRepository(uow.session, current_user.id),
        SqlJournalRepository(uow.session, current_user.id),
        SqlJournalResponseRepository(uow.session, current_user.id),
        clock,
    ).record_movement(
        movement_type=payload.type,
        account_id=payload.account_id,
        category_id=payload.category_id,
        amount=payload.amount,
        accounting_date=payload.date,
        note=payload.note,
        idempotency_key=idempotency_key,
    )
    uow.commit()
    return MovementCreateResponse.model_validate(result.body)


@router.post("/{movement_id}/void", response_model=VoidMovementResponse)
def void_movement(
    movement_id: uuid.UUID,
    current_user: CurrentUserDep,
    uow: UnitOfWorkDep,
) -> VoidMovementResponse:
    result = VoidService(
        SqlAccountRepository(uow.session, current_user.id),
        SqlJournalRepository(uow.session, current_user.id),
        clock,
    ).void_movement(movement_id)
    uow.commit()
    return VoidMovementResponse(
        void_movement=VoidMovementSummary(
            id=result.journal.id,
            voided_journal_id=movement_id,
            date=result.journal.date,
        ),
        new_balance=result.new_balance,
        negative_balance_warning=result.negative_balance_warning,
    )


@router.get("", response_model=MovementHistoryResponse)
def list_movements(
    current_user: CurrentUserDep,
    uow: UnitOfWorkDep,
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> MovementHistoryResponse:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise DomainValidationError(
            "La fecha inicial no puede ser posterior a la fecha final",
            field="date_from",
        )
    items, total = SqlJournalRepository(uow.session, current_user.id).list_paginated(
        account_id=account_id,
        category_id=category_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return MovementHistoryResponse(
        items=[_history_item(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


def _history_item(journal: Journal) -> MovementHistoryItem:
    account_line = next(line for line in journal.lines if line.account_id is not None)
    category_line = next((line for line in journal.lines if line.category_id is not None), None)
    if account_line.account is None:
        raise RuntimeError("Journal account relationship is missing")
    if category_line is not None and category_line.category is None:
        raise RuntimeError("Journal category relationship is missing")
    journal_type = cast(Literal["OPENING", "INCOME", "EXPENSE", "VOID"], journal.kind)
    journal_status = cast(Literal["POSTED", "VOIDED"], journal.status)
    return MovementHistoryItem(
        id=journal.id,
        type=journal_type,
        status=journal_status,
        date=journal.date,
        amount=Decimal(account_line.amount),
        note=journal.note,
        account=ResourceSummary(id=account_line.account.id, name=account_line.account.name),
        category=(
            ResourceSummary(id=category_line.category.id, name=category_line.category.name)
            if category_line is not None and category_line.category is not None
            else None
        ),
    )
