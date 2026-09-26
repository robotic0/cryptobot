"""P2P marketplace with escrow.

Trade lifecycle::

    take offer ─▶ ESCROW_LOCKED ─(buyer pays)─▶ FIAT_PAID ─(seller releases)─▶ COMPLETED
                      │
                      └─(either side cancels before payment)─▶ CANCELLED

On ``ESCROW_LOCKED`` the seller's crypto is moved into their locked balance;
it is only ever released to the buyer or returned to the seller.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Offer,
    OfferSide,
    OfferStatus,
    Trade,
    TradeStatus,
)
from app.services.wallet import WalletService
from app.utils.money import quantize_crypto, quantize_fiat


class TradeError(Exception):
    """Raised when a trade action is invalid for the current state."""


class EscrowService:
    def __init__(self, session: AsyncSession, fee_rate: Decimal) -> None:
        self._session = session
        self._wallet = WalletService(session)
        self._fee_rate = fee_rate

    # --- offers -----------------------------------------------------------
    async def create_offer(
        self,
        *,
        maker_id: int,
        side: OfferSide,
        asset: str,
        amount: Decimal,
        price_usd: Decimal,
        payment_method: str,
    ) -> Offer:
        amount = quantize_crypto(amount)
        price_usd = quantize_fiat(price_usd)
        if amount <= 0 or price_usd <= 0:
            raise TradeError("Miqdor va narx noldan katta bo‘lishi kerak.")
        offer = Offer(
            maker_id=maker_id,
            side=side,
            asset=asset.upper(),
            amount=amount,
            remaining=amount,
            price_usd=price_usd,
            payment_method=payment_method,
        )
        self._session.add(offer)
        await self._session.flush()
        return offer

    async def open_offers(self, asset: str | None = None) -> list[Offer]:
        stmt = select(Offer).where(Offer.status == OfferStatus.OPEN)
        if asset:
            stmt = stmt.where(Offer.asset == asset.upper())
        result = await self._session.scalars(stmt.order_by(Offer.created_at.desc()))
        return list(result)

    async def cancel_offer(self, offer_id: int, maker_id: int) -> None:
        offer = await self._session.get(Offer, offer_id)
        if offer is None or offer.maker_id != maker_id:
            raise TradeError("Taklif topilmadi.")
        if offer.status != OfferStatus.OPEN:
            raise TradeError("Bu taklifni bekor qilib bo‘lmaydi.")
        offer.status = OfferStatus.CANCELLED

    # --- trades -----------------------------------------------------------
    async def take_offer(
        self, *, offer_id: int, taker_id: int, amount: Decimal
    ) -> Trade:
        offer = await self._session.get(Offer, offer_id)
        if offer is None or offer.status != OfferStatus.OPEN:
            raise TradeError("Taklif mavjud emas yoki yopilgan.")
        if offer.maker_id == taker_id:
            raise TradeError("O‘z taklifingizni qabul qila olmaysiz.")

        amount = quantize_crypto(amount)
        if amount <= 0 or amount > offer.remaining:
            raise TradeError("Noto‘g‘ri miqdor.")

        if offer.side is OfferSide.SELL:
            seller_id, buyer_id = offer.maker_id, taker_id
        else:  # BUY offer: the taker is the one selling crypto
            seller_id, buyer_id = taker_id, offer.maker_id

        # Lock the seller's crypto in escrow (raises if insufficient).
        await self._wallet.lock(seller_id, offer.asset, amount, ref=f"offer:{offer.id}")

        fiat_total = quantize_fiat(amount * offer.price_usd)
        fee = quantize_crypto(amount * self._fee_rate)
        trade = Trade(
            offer_id=offer.id,
            seller_id=seller_id,
            buyer_id=buyer_id,
            asset=offer.asset,
            amount=amount,
            price_usd=offer.price_usd,
            fiat_total=fiat_total,
            fee=fee,
            status=TradeStatus.ESCROW_LOCKED,
        )
        self._session.add(trade)

        offer.remaining = quantize_crypto(offer.remaining - amount)
        if offer.remaining <= 0:
            offer.status = OfferStatus.CLOSED
        await self._session.flush()
        return trade

    async def mark_fiat_paid(self, trade_id: int, buyer_id: int) -> Trade:
        trade = await self._require_trade(trade_id)
        if trade.buyer_id != buyer_id:
            raise TradeError("Faqat xaridor to‘lovni tasdiqlashi mumkin.")
        if trade.status != TradeStatus.ESCROW_LOCKED:
            raise TradeError("Bu bosqichda to‘lovni belgilab bo‘lmaydi.")
        trade.status = TradeStatus.FIAT_PAID
        return trade

    async def release(self, trade_id: int, seller_id: int) -> Trade:
        trade = await self._require_trade(trade_id)
        if trade.seller_id != seller_id:
            raise TradeError("Faqat sotuvchi mablag‘ni chiqarishi mumkin.")
        if trade.status != TradeStatus.FIAT_PAID:
            raise TradeError("Avval xaridor to‘lovni tasdiqlashi kerak.")
        await self._wallet.release_from_escrow(
            seller_id=trade.seller_id,
            buyer_id=trade.buyer_id,
            asset=trade.asset,
            amount=trade.amount,
            fee=trade.fee,
            ref=f"trade:{trade.id}",
        )
        trade.status = TradeStatus.COMPLETED
        return trade

    async def cancel_trade(self, trade_id: int, actor_id: int) -> Trade:
        trade = await self._require_trade(trade_id)
        if actor_id not in (trade.seller_id, trade.buyer_id):
            raise TradeError("Siz bu savdoning ishtirokchisi emassiz.")
        if trade.status != TradeStatus.ESCROW_LOCKED:
            raise TradeError("To‘lov belgilangach bekor qilib bo‘lmaydi — nizo oching.")
        # Return the escrowed crypto to the seller.
        await self._wallet.unlock(
            trade.seller_id, trade.asset, trade.amount, ref=f"trade:{trade.id}"
        )
        trade.status = TradeStatus.CANCELLED
        return trade

    async def dispute(self, trade_id: int, actor_id: int) -> Trade:
        trade = await self._require_trade(trade_id)
        if actor_id not in (trade.seller_id, trade.buyer_id):
            raise TradeError("Siz bu savdoning ishtirokchisi emassiz.")
        if trade.status not in (TradeStatus.ESCROW_LOCKED, TradeStatus.FIAT_PAID):
            raise TradeError("Bu savdo uchun nizo ochib bo‘lmaydi.")
        trade.status = TradeStatus.DISPUTED
        return trade

    async def _require_trade(self, trade_id: int) -> Trade:
        trade = await self._session.get(Trade, trade_id)
        if trade is None:
            raise TradeError("Savdo topilmadi.")
        return trade
