from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, PlainSerializer

from app.domain.money import MoneyError, parse_money


def _parse_positive_money(value: object) -> Decimal:
    try:
        return parse_money(value)  # type: ignore[arg-type]
    except MoneyError as error:
        raise ValueError(str(error)) from error


def _parse_non_negative_money(value: object) -> Decimal:
    try:
        return parse_money(value, allow_zero=True)  # type: ignore[arg-type]
    except MoneyError as error:
        raise ValueError(str(error)) from error


def _parse_signed_money(value: object) -> Decimal:
    if isinstance(value, float) or not isinstance(value, (str, Decimal)):
        raise ValueError("El monto debe enviarse como texto decimal")
    try:
        amount = Decimal(value)
    except Exception as error:
        raise ValueError("El monto no es un decimal válido") from error
    exponent = amount.as_tuple().exponent
    if not amount.is_finite():
        raise ValueError("El monto debe ser finito")
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError("El monto admite máximo dos decimales")
    return amount.quantize(Decimal("0.01"))


def format_money(value: Decimal) -> str:
    return f"{value:.2f}"


PositiveMoney = Annotated[
    Decimal,
    BeforeValidator(_parse_positive_money),
    PlainSerializer(format_money, return_type=str),
]
NonNegativeMoney = Annotated[
    Decimal,
    BeforeValidator(_parse_non_negative_money),
    PlainSerializer(format_money, return_type=str),
]
Money = Annotated[
    Decimal,
    BeforeValidator(_parse_signed_money),
    PlainSerializer(format_money, return_type=str),
]


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    detail: list[ErrorDetail]
