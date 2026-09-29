from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.domain.money import sum_money


class AccountStore(Protocol):
    def list_with_balances(self, *, status: str | None = None) -> list[tuple[Any, Decimal]]: ...


@dataclass(frozen=True)
class AccountBalance:
    account: Any
    balance: Decimal


@dataclass(frozen=True)
class BalanceResult:
    consolidated_balance: Decimal
    currency: str
    accounts: list[AccountBalance]


class BalanceService:
    def __init__(self, accounts: AccountStore) -> None:
        self._accounts = accounts

    def get_balance(self, *, currency: str) -> BalanceResult:
        account_balances = [
            AccountBalance(account=account, balance=balance)
            for account, balance in self._accounts.list_with_balances(status="ACTIVE")
        ]
        return BalanceResult(
            consolidated_balance=sum_money(item.balance for item in account_balances),
            currency=currency,
            accounts=account_balances,
        )
