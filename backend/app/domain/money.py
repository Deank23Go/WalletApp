from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")
MAX_MONEY = Decimal("99999999999999999.99")


class MoneyError(ValueError):
    pass


def parse_money(value: str | Decimal, *, allow_zero: bool = False) -> Decimal:
    if isinstance(value, float) or not isinstance(value, (str, Decimal)):
        raise MoneyError("El monto debe enviarse como texto decimal")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise MoneyError("El monto no es un decimal válido") from error
    if not amount.is_finite():
        raise MoneyError("El monto debe ser finito")
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise MoneyError("El monto admite máximo dos decimales")
    amount = amount.quantize(CENT)
    if amount > MAX_MONEY:
        raise MoneyError("El monto excede el máximo permitido")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise MoneyError("El monto debe ser mayor que cero")
    return amount


def sum_money(amounts: Iterable[Decimal]) -> Decimal:
    return sum(amounts, Decimal("0.00")).quantize(CENT)
