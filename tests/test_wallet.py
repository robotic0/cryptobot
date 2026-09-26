"""Ledger correctness: balances, atomicity of lock/unlock, no negatives."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.wallet import InsufficientFunds, WalletService

BTC = "BTC"
ALICE, BOB = 1, 2


async def test_credit_then_balance(session):
    wallet = WalletService(session)
    await wallet.credit(ALICE, BTC, Decimal("1.5"))
    available, locked = await wallet.get(ALICE, BTC)
    assert available == Decimal("1.5")
    assert locked == Decimal("0")


async def test_debit_insufficient_raises(session):
    wallet = WalletService(session)
    await wallet.credit(ALICE, BTC, Decimal("1"))
    with pytest.raises(InsufficientFunds):
        await wallet.debit(ALICE, BTC, Decimal("2"))
    # Balance must be unchanged after a failed debit.
    available, _ = await wallet.get(ALICE, BTC)
    assert available == Decimal("1")


async def test_lock_moves_available_to_locked(session):
    wallet = WalletService(session)
    await wallet.credit(ALICE, BTC, Decimal("2"))
    await wallet.lock(ALICE, BTC, Decimal("0.75"))
    available, locked = await wallet.get(ALICE, BTC)
    assert available == Decimal("1.25")
    assert locked == Decimal("0.75")


async def test_lock_more_than_available_raises(session):
    wallet = WalletService(session)
    await wallet.credit(ALICE, BTC, Decimal("1"))
    with pytest.raises(InsufficientFunds):
        await wallet.lock(ALICE, BTC, Decimal("1.5"))


async def test_unlock_returns_to_available(session):
    wallet = WalletService(session)
    await wallet.credit(ALICE, BTC, Decimal("2"))
    await wallet.lock(ALICE, BTC, Decimal("2"))
    await wallet.unlock(ALICE, BTC, Decimal("2"))
    available, locked = await wallet.get(ALICE, BTC)
    assert available == Decimal("2")
    assert locked == Decimal("0")


async def test_release_from_escrow_conserves_value_with_fee(session):
    wallet = WalletService(session)
    await wallet.credit(ALICE, BTC, Decimal("1"))
    await wallet.lock(ALICE, BTC, Decimal("1"))

    net = await wallet.release_from_escrow(
        seller_id=ALICE, buyer_id=BOB, asset=BTC,
        amount=Decimal("1"), fee=Decimal("0.01"),
    )
    assert net == Decimal("0.99")

    a_avail, a_locked = await wallet.get(ALICE, BTC)
    b_avail, b_locked = await wallet.get(BOB, BTC)
    assert a_avail == Decimal("0")
    assert a_locked == Decimal("0")
    assert b_avail == Decimal("0.99")
    assert b_locked == Decimal("0")


async def test_ledger_records_every_move(session):
    from sqlalchemy import func, select

    from app.database.models import LedgerEntry

    wallet = WalletService(session)
    await wallet.credit(ALICE, BTC, Decimal("1"))
    await wallet.lock(ALICE, BTC, Decimal("1"))
    await wallet.release_from_escrow(
        seller_id=ALICE, buyer_id=BOB, asset=BTC,
        amount=Decimal("1"), fee=Decimal("0.01"),
    )
    count = await session.scalar(select(func.count()).select_from(LedgerEntry))
    # deposit + lock + trade_out + trade_in + fee = 5
    assert count == 5
