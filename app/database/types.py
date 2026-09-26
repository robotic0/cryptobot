"""A SQLAlchemy type that stores Decimals exactly, even on SQLite.

SQLite's ``REAL`` affinity would coerce numeric columns to floats and lose
precision — unacceptable for money. We serialise Decimals as text instead.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class DecimalText(TypeDecorator):
    """Stores a :class:`~decimal.Decimal` as a fixed-format string."""

    impl = String(64)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return format(value, "f")

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        return Decimal(value)
