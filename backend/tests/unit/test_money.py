from decimal import Decimal

import pytest

from app.domain.money import MAX_MONEY, MoneyError, parse_money, sum_money


@pytest.mark.parametrize(
    "value",
    ["0", "-1", "0.001", "10.999", "NaN", "Infinity", "-Infinity", "100000000000000000.00"],
)
def test_parse_money_rejects_invalid_boundaries(value: str) -> None:
    with pytest.raises(MoneyError):
        parse_money(value)


def test_parse_money_accepts_minimum_cent_and_numeric_maximum() -> None:
    assert parse_money("0.01") == Decimal("0.01")
    assert parse_money(str(MAX_MONEY)) == MAX_MONEY


def test_parse_money_allows_zero_only_when_explicit() -> None:
    assert parse_money("0", allow_zero=True) == Decimal("0.00")
    with pytest.raises(MoneyError, match="mayor que cero"):
        parse_money("0")


def test_parse_money_rejects_float_and_invalid_text() -> None:
    for value in (1.5, "abc"):
        with pytest.raises(MoneyError):
            parse_money(value)


def test_sum_money_uses_exact_decimal_arithmetic() -> None:
    assert sum_money((Decimal("0.1"), Decimal("0.2"))) == Decimal("0.30")
