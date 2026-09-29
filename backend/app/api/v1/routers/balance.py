from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.deps import CurrentUserDep, UnitOfWorkDep
from app.domain.services.balance_service import BalanceService
from app.repositories.accounts_repo import SqlAccountRepository
from app.schemas.balance import AccountBalanceResponse, BalanceResponse

router = APIRouter(tags=["balance"])


@router.get("/balance", response_model=BalanceResponse)
def get_balance(current_user: CurrentUserDep, uow: UnitOfWorkDep) -> BalanceResponse:
    result = BalanceService(SqlAccountRepository(uow.session, current_user.id)).get_balance(
        currency=current_user.preferred_currency
    )
    return BalanceResponse(
        consolidated_balance=result.consolidated_balance,
        currency=result.currency,
        accounts=[
            AccountBalanceResponse(
                id=item.account.id,
                name=item.account.name,
                type=item.account.type,
                balance=item.balance,
            )
            for item in result.accounts
        ],
    )
