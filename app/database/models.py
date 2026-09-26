"""ORM models: users, balances, ledger, P2P offers/trades and audit log."""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.types import DecimalText


class OfferSide(enum.StrEnum):
    BUY = "buy"    # maker wants to buy crypto (pays fiat)
    SELL = "sell"  # maker wants to sell crypto (receives fiat)


class OfferStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TradeStatus(enum.StrEnum):
    ESCROW_LOCKED = "escrow_locked"  # seller's crypto is held in escrow
    FIAT_PAID = "fiat_paid"          # buyer marked the fiat payment as sent
    COMPLETED = "completed"          # seller released; crypto delivered
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class LedgerKind(enum.StrEnum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    ESCROW_LOCK = "escrow_lock"
    ESCROW_UNLOCK = "escrow_unlock"
    TRADE_IN = "trade_in"
    TRADE_OUT = "trade_out"
    FEE = "fee"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # chat_id
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    balances: Mapped[list[Balance]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Balance(Base):
    """Available + escrow-locked balance for one (user, asset) pair."""

    __tablename__ = "balances"
    __table_args__ = (UniqueConstraint("user_id", "asset", name="uq_user_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    asset: Mapped[str] = mapped_column(String(16), index=True)
    available: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    locked: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    user: Mapped[User] = relationship(back_populates="balances")


class LedgerEntry(Base):
    """Append-only audit record of every balance movement."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    asset: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(DecimalText)  # signed
    kind: Mapped[LedgerKind] = mapped_column(Enum(LedgerKind))
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maker_id: Mapped[int] = mapped_column(BigInteger, index=True)
    side: Mapped[OfferSide] = mapped_column(Enum(OfferSide))
    asset: Mapped[str] = mapped_column(String(16), index=True)
    price_usd: Mapped[Decimal] = mapped_column(DecimalText)  # price per 1 unit
    amount: Mapped[Decimal] = mapped_column(DecimalText)
    remaining: Mapped[Decimal] = mapped_column(DecimalText)
    payment_method: Mapped[str] = mapped_column(String(64))
    status: Mapped[OfferStatus] = mapped_column(
        Enum(OfferStatus), default=OfferStatus.OPEN, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), index=True)
    seller_id: Mapped[int] = mapped_column(BigInteger, index=True)
    buyer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    asset: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(DecimalText)
    price_usd: Mapped[Decimal] = mapped_column(DecimalText)
    fiat_total: Mapped[Decimal] = mapped_column(DecimalText)
    fee: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus), default=TradeStatus.ESCROW_LOCKED, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
