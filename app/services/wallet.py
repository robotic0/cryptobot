"""The custodial ledger.

⚠️  This is a *simulated* internal ledger for demonstration and education.
It does not hold real private keys or broadcast real blockchain transactions.
Deposits and withdrawals move balances within this database only.

Every mutation is written both to the :class:`Balance` row and to an
append-only :class:`LedgerEntry`, and no balance can ever go negative.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Balance, LedgerEntry, LedgerKind
from app.utils.money import quantize_crypto


class InsufficientFunds(Exception):
    def __init__(self, asset: str, requested: Decimal, available: Decimal) -> None:
        super().__init__(
            f"{asset}: yetarli mablag‘ yo‘q "
            f"(kerak {requested}, mavjud {available})"
        )
        self.asset = asset
        self.requested = requested
        self.available = available


class WalletService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _balance(self, user_id: int, asset: str) -> Balance:
        result = await self._session.scalars(
            select(Balance).where(
                Balance.user_id == user_id, Balance.asset == asset
            )
        )
        balance = result.first()
        if balance is None:
            balance = Balance(
                user_id=user_id,
                asset=asset,
                available=Decimal("0"),
                locked=Decimal("0"),
            )
            self._session.add(balance)
            await self._session.flush()
        return balance

    async def get(self, user_id: int, asset: str) -> tuple[Decimal, Decimal]:
        balance = await self._balance(user_id, asset)
        return balance.available, balance.locked

    async def all_balances(self, user_id: int) -> list[Balance]:
        result = await self._session.scalars(
            select(Balance).where(
                Balance.user_id == user_id
            ).order_by(Balance.asset)
        )
        return [b for b in result if b.available > 0 or b.locked > 0]

    def _log(
        self, user_id: int, asset: str, amount: Decimal,
        kind: LedgerKind, ref: str | None,
    ) -> None:
        self._session.add(
            LedgerEntry(
                user_id=user_id, asset=asset, amount=amount, kind=kind, ref=ref
            )
        )

    async def credit(
        self, user_id: int, asset: str, amount: Decimal,
        kind: LedgerKind = LedgerKind.DEPOSIT, ref: str | None = None,
    ) -> None:
        amount = quantize_crypto(amount)
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        balance = await self._balance(user_id, asset)
        balance.available += amount
        self._log(user_id, asset, amount, kind, ref)

    async def debit(
        self, user_id: int, asset: str, amount: Decimal,
        kind: LedgerKind = LedgerKind.WITHDRAW, ref: str | None = None,
    ) -> None:
        amount = quantize_crypto(amount)
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        balance = await self._balance(user_id, asset)
        if balance.available < amount:
            raise InsufficientFunds(asset, amount, balance.available)
        balance.available -= amount
        self._log(user_id, asset, -amount, kind, ref)

    async def lock(
        self, user_id: int, asset: str, amount: Decimal, ref: str | None = None
    ) -> None:
        """Move funds from available into escrow-locked."""
        amount = quantize_crypto(amount)
        balance = await self._balance(user_id, asset)
        if balance.available < amount:
            raise InsufficientFunds(asset, amount, balance.available)
        balance.available -= amount
        balance.locked += amount
        self._log(user_id, asset, -amount, LedgerKind.ESCROW_LOCK, ref)

    async def unlock(
        self, user_id: int, asset: str, amount: Decimal, ref: str | None = None
    ) -> None:
        """Return escrow-locked funds to available (e.g. cancelled trade)."""
        amount = quantize_crypto(amount)
        balance = await self._balance(user_id, asset)
        if balance.locked < amount:
            raise InsufficientFunds(f"{asset} (locked)", amount, balance.locked)
        balance.locked -= amount
        balance.available += amount
        self._log(user_id, asset, amount, LedgerKind.ESCROW_UNLOCK, ref)

    async def release_from_escrow(
        self,
        *,
        seller_id: int,
        buyer_id: int,
        asset: str,
        amount: Decimal,
        fee: Decimal = Decimal("0"),
        ref: str | None = None,
    ) -> Decimal:
        """Settle a trade: move the seller's locked funds to the buyer.

        Returns the net amount credited to the buyer (``amount - fee``).
        """
        amount = quantize_crypto(amount)
        fee = quantize_crypto(fee)
        if fee < 0 or fee > amount:
            raise ValueError("Invalid fee")

        seller = await self._balance(seller_id, asset)
        if seller.locked < amount:
            raise InsufficientFunds(f"{asset} (locked)", amount, seller.locked)

        net = amount - fee
        seller.locked -= amount
        self._log(seller_id, asset, -amount, LedgerKind.TRADE_OUT, ref)

        buyer = await self._balance(buyer_id, asset)
        buyer.available += net
        self._log(buyer_id, asset, net, LedgerKind.TRADE_IN, ref)

        if fee > 0:
            self._log(seller_id, asset, -fee, LedgerKind.FEE, ref)
        return net
