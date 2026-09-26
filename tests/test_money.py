"""Unit tests for money parsing/formatting (no DB, no network)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.utils.money import (
    InvalidAmount,
    format_crypto,
    format_fiat,
    parse_positive_crypto,
    quantize_crypto,
)


def test_parse_accepts_comma_decimal():
    assert parse_positive_crypto("0,5") == Decimal("0.5")


def test_parse_truncates_to_eight_dp():
    # 9 dp -> truncated (rounded down) to 8
    assert parse_positive_crypto("0.123456789") == Decimal("0.12345678")


def test_parse_rejects_zero():
    with pytest.raises(InvalidAmount):
        parse_positive_crypto("0")


def test_parse_rejects_negative():
    with pytest.raises(InvalidAmount):
        parse_positive_crypto("-1")


def test_parse_rejects_junk():
    with pytest.raises(InvalidAmount):
        parse_positive_crypto("abc")


def test_parse_rejects_infinity():
    with pytest.raises(InvalidAmount):
        parse_positive_crypto("Infinity")


def test_format_crypto_has_no_trailing_zeros():
    assert format_crypto(Decimal("1.50000000")) == "1.5"
    assert format_crypto(Decimal("2")) == "2"


def test_format_fiat_groups_thousands():
    assert format_fiat(Decimal("1234567.5")) == "1,234,567.50"


def test_quantize_is_round_down():
    assert quantize_crypto(Decimal("0.999999999")) == Decimal("0.99999999")
