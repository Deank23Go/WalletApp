from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, status

from app.api.v1.deps import CurrentUserDep, IdempotencyKeyDep, UnitOfWorkDep
from app.core.idempotency import IdempotencyCoordinator
from app.core.security import SystemClock
from app.domain.ports import JsonObject
from app.domain.services.account_service import AccountService
from app.repositories.accounts_repo import SqlAccountRepository
from app.repositories.journal_responses_repo import SqlJournalResponseRepository
from app.repositories.journals_repo import SqlJournalRepository
from app.schemas.accounts import AccountCreateRequest, AccountResponse, AccountUpdateRequest

router = APIRouter(prefix="/accounts", tags=["accounts"])
clock = SystemClock()


def _response(account: Any, balance: Decimal, currency: str) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        type=account.type,
        status=account.status,
        balance=balance,
        currency=currency,
    )


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreateRequest,
    current_user: CurrentUserDep,
    idempotency_key: IdempotencyKeyDep,
    uow: UnitOfWorkDep,
) -> AccountResponse:
    responses = SqlJournalResponseRepository(uow.session, current_user.id)
    coordinator = IdempotencyCoordinator(responses, operation="account.create")
    replay = coordinator.claim_or_replay(idempotency_key)
    if replay is not None:
        return AccountResponse.model_validate(replay.body)
    accounts = SqlAccountRepository(uow.session, current_user.id)
    account = AccountService(
        accounts,
        SqlJournalRepository(uow.session, current_user.id),
        clock,
    ).create_account(
        name=payload.name,
        account_type=payload.type,
        opening_balance=payload.opening_balance,
        idempotency_key=idempotency_key,
    )
    balance = accounts.get_balance(account.id)
    if balance is None:
        from app.domain.errors import ResourceNotFoundError

        raise ResourceNotFoundError("La cuenta no existe", field="account_id")
    result = _response(account, balance, current_user.preferred_currency)
    coordinator.complete(
        idempotency_key,
        status_code=201,
        response=cast(JsonObject, result.model_dump(mode="json")),
    )
    uow.commit()
    return result


@router.get("", response_model=list[AccountResponse])
def list_accounts(current_user: CurrentUserDep, uow: UnitOfWorkDep) -> list[AccountResponse]:
    accounts = SqlAccountRepository(uow.session, current_user.id)
    return [
        _response(account, balance, current_user.preferred_currency)
        for account, balance in accounts.list_with_balances()
    ]


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdateRequest,
    current_user: CurrentUserDep,
    uow: UnitOfWorkDep,
) -> AccountResponse:
    accounts = SqlAccountRepository(uow.session, current_user.id)
    service = AccountService(accounts, SqlJournalRepository(uow.session, current_user.id), clock)
    account = (
        service.rename_account(account_id, payload.name)
        if payload.name is not None
        else service.deactivate_account(account_id)
    )
    balance = accounts.get_balance(account.id)
    if balance is None:
        from app.domain.errors import ResourceNotFoundError

        raise ResourceNotFoundError("La cuenta no existe", field="account_id")
    uow.commit()
    return _response(account, balance, current_user.preferred_currency)
