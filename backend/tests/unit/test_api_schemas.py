import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.accounts import AccountCreateRequest, AccountResponse
from app.schemas.movements import MovementCreateRequest, MovementFilters


def test_money_schema_accepts_decimal_string_serializes_two_places_and_rejects_float() -> None:
    request = AccountCreateRequest(name="Cash", type="CASH", opening_balance="150000.00")
    response = AccountResponse(
        id=uuid.uuid4(),
        name="Cash",
        type="CASH",
        status="ACTIVE",
        balance=Decimal("1.2"),
        currency="COP",
    )

    assert request.opening_balance == Decimal("150000.00")
    assert response.model_dump(mode="json")["balance"] == "1.20"
    with pytest.raises(ValidationError):
        AccountCreateRequest(name="Cash", type="CASH", opening_balance=150000.0)


def test_movement_schema_reports_amount_and_filter_limits() -> None:
    base = {
        "type": "INCOME",
        "account_id": uuid.uuid4(),
        "category_id": uuid.uuid4(),
        "date": date(2026, 9, 28),
    }

    with pytest.raises(ValidationError) as error:
        MovementCreateRequest(**base, amount="abc")
    assert error.value.errors()[0]["loc"] == ("amount",)
    with pytest.raises(ValidationError):
        MovementFilters(page_size=101)
    with pytest.raises(ValidationError, match="fecha inicial"):
        MovementFilters(date_from=date(2026, 9, 29), date_to=date(2026, 9, 28))
