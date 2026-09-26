"""P2P trade lifecycle: escrow locking, release, cancel and guard rails."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.database.models import OfferSide, TradeStatus
from app.services.escrow import EscrowService, TradeError
from app.services.wallet import WalletService

BTC = "BTC"
SELLER, BUYER = 10, 20
FEE_RATE = Decimal("0.01")


async def _seed_seller(session, amount="1"):
    wallet = WalletService(session)
    await wallet.credit(SELLER, BTC, Decimal(amount))


async def test_happy_path_sell_offer(session):
    await _seed_seller(session, "1")
    escrow = EscrowService(session, FEE_RATE)

    offer = await escrow.create_offer(
        maker_id=SELLER, side=OfferSide.SELL, asset=BTC,
        amount=Decimal("1"), price_usd=Decimal("60000"),
        payment_method="Bank transfer",
    )
    trade = await escrow.take_offer(
        offer_id=offer.id, taker_id=BUYER, amount=Decimal("1")
    )
    assert trade.status == TradeStatus.ESCROW_LOCKED
    assert trade.fiat_total == Decimal("60000.00")

    # Seller's BTC is now locked.
    wallet = WalletService(session)
    avail, locked = await wallet.get(SELLER, BTC)
    assert avail == Decimal("0")
    assert locked == Decimal("1")

    await escrow.mark_fiat_paid(trade.id, buyer_id=BUYER)
    await escrow.release(trade.id, seller_id=SELLER)
    assert trade.status == TradeStatus.COMPLETED

    b_avail, _ = await wallet.get(BUYER, BTC)
    assert b_avail == Decimal("0.99")  # 1 - 1% fee


async def test_cannot_release_before_payment(session):
    await _seed_seller(session)
    escrow = EscrowService(session, FEE_RATE)
    offer = await escrow.create_offer(
        maker_id=SELLER, side=OfferSide.SELL, asset=BTC,
        amount=Decimal("1"), price_usd=Decimal("60000"),
        payment_method="Cash",
    )
    trade = await escrow.take_offer(
        offer_id=offer.id, taker_id=BUYER, amount=Decimal("1")
    )
    with pytest.raises(TradeError):
        await escrow.release(trade.id, seller_id=SELLER)


async def test_cannot_take_own_offer(session):
    await _seed_seller(session)
    escrow = EscrowService(session, FEE_RATE)
    offer = await escrow.create_offer(
        maker_id=SELLER, side=OfferSide.SELL, asset=BTC,
        amount=Decimal("1"), price_usd=Decimal("60000"),
        payment_method="Cash",
    )
    with pytest.raises(TradeError):
        await escrow.take_offer(
            offer_id=offer.id, taker_id=SELLER, amount=Decimal("1")
        )


async def test_take_offer_without_funds_raises(session):
    # Seller has no balance -> escrow lock must fail.
    escrow = EscrowService(session, FEE_RATE)
    offer = await escrow.create_offer(
        maker_id=SELLER, side=OfferSide.SELL, asset=BTC,
        amount=Decimal("1"), price_usd=Decimal("60000"),
        payment_method="Cash",
    )
    from app.services.wallet import InsufficientFunds

    with pytest.raises(InsufficientFunds):
        await escrow.take_offer(
            offer_id=offer.id, taker_id=BUYER, amount=Decimal("1")
        )


async def test_cancel_returns_escrow_to_seller(session):
    await _seed_seller(session, "1")
    escrow = EscrowService(session, FEE_RATE)
    offer = await escrow.create_offer(
        maker_id=SELLER, side=OfferSide.SELL, asset=BTC,
        amount=Decimal("1"), price_usd=Decimal("60000"),
        payment_method="Cash",
    )
    trade = await escrow.take_offer(
        offer_id=offer.id, taker_id=BUYER, amount=Decimal("1")
    )
    await escrow.cancel_trade(trade.id, actor_id=BUYER)
    assert trade.status == TradeStatus.CANCELLED

    wallet = WalletService(session)
    avail, locked = await wallet.get(SELLER, BTC)
    assert avail == Decimal("1")
    assert locked == Decimal("0")


async def test_partial_fill_updates_remaining(session):
    await _seed_seller(session, "2")
    escrow = EscrowService(session, FEE_RATE)
    offer = await escrow.create_offer(
        maker_id=SELLER, side=OfferSide.SELL, asset=BTC,
        amount=Decimal("2"), price_usd=Decimal("60000"),
        payment_method="Cash",
    )
    await escrow.take_offer(
        offer_id=offer.id, taker_id=BUYER, amount=Decimal("0.5")
    )
    assert offer.remaining == Decimal("1.5")


async def test_overfill_rejected(session):
    await _seed_seller(session, "1")
    escrow = EscrowService(session, FEE_RATE)
    offer = await escrow.create_offer(
        maker_id=SELLER, side=OfferSide.SELL, asset=BTC,
        amount=Decimal("1"), price_usd=Decimal("60000"),
        payment_method="Cash",
    )
    with pytest.raises(TradeError):
        await escrow.take_offer(
            offer_id=offer.id, taker_id=BUYER, amount=Decimal("2")
        )
