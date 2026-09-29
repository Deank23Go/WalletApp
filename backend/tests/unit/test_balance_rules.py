from decimal import Decimal
from types import SimpleNamespace

from app.domain.services.balance_service import BalanceService


class FakeAccounts:
    def __init__(self, rows):
        self.rows = rows
        self.requested_status = None

    def list_with_balances(self, *, status=None):
        self.requested_status = status
        return [(account, balance) for account, balance in self.rows if status is None or account.status == status]


def test_balance_service_sums_exact_decimals_and_excludes_inactive_accounts() -> None:
    store = FakeAccounts(
        [
            (SimpleNamespace(status="ACTIVE"), Decimal("0.10")),
            (SimpleNamespace(status="ACTIVE"), Decimal("0.20")),
            (SimpleNamespace(status="INACTIVE"), Decimal("99.00")),
        ]
    )

    result = BalanceService(store).get_balance(currency="COP")

    assert store.requested_status == "ACTIVE"
    assert result.consolidated_balance == Decimal("0.30")
    assert [item.balance for item in result.accounts] == [Decimal("0.10"), Decimal("0.20")]


def test_balance_service_returns_zero_without_accounts() -> None:
    result = BalanceService(FakeAccounts([])).get_balance(currency="COP")

    assert result.consolidated_balance == Decimal("0.00")
    assert result.accounts == []
