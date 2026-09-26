"""Money helpers. Crypto amounts are always :class:`~decimal.Decimal` and
never floats — floating point silently loses value.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, InvalidOperation

# Smallest unit we track (8 decimal places, like a satoshi).
CRYPTO_QUANT = Decimal("0.00000001")
FIAT_QUANT = Decimal("0.01")


class InvalidAmount(ValueError):
    """Raised when a user-supplied amount cannot be used as money."""


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """Parse an untrusted value into a Decimal, rejecting junk and NaN/Inf."""
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidAmount(f"Noto‘g‘ri miqdor: {value!r}") from exc
    if not result.is_finite():
        raise InvalidAmount("Miqdor cheksiz bo‘lishi mumkin emas.")
    return result


def quantize_crypto(value: Decimal) -> Decimal:
    return value.quantize(CRYPTO_QUANT, rounding=ROUND_DOWN)


def quantize_fiat(value: Decimal) -> Decimal:
    return value.quantize(FIAT_QUANT, rounding=ROUND_DOWN)


def parse_positive_crypto(value: str) -> Decimal:
    """Parse and validate a strictly-positive crypto amount."""
    amount = quantize_crypto(to_decimal(value))
    if amount <= 0:
        raise InvalidAmount("Miqdor noldan katta bo‘lishi kerak.")
    return amount


def format_crypto(value: Decimal) -> str:
    """Human-friendly crypto amount without trailing zeros."""
    q = quantize_crypto(value).normalize()
    # normalize() can produce exponent form for whole numbers; expand it.
    return f"{q:f}"


def format_fiat(value: Decimal) -> str:
    return f"{quantize_fiat(value):,.2f}"
