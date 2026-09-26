"""Taking offers and driving the escrow trade lifecycle."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Trade, TradeStatus
from app.keyboards.inline import OfferCB, TradeCB, trade_actions
from app.services.escrow import EscrowService, TradeError
from app.services.wallet import InsufficientFunds
from app.states import TakeOffer
from app.utils.money import (
    InvalidAmount,
    format_crypto,
    format_fiat,
    parse_positive_crypto,
)

router = Router(name="trades")

_STATUS_LABEL = {
    TradeStatus.ESCROW_LOCKED: "🔒 Eskrouda",
    TradeStatus.FIAT_PAID: "💸 To‘lov qilindi",
    TradeStatus.COMPLETED: "✅ Yakunlandi",
    TradeStatus.CANCELLED: "❌ Bekor qilindi",
    TradeStatus.DISPUTED: "⚠️ Nizoda",
}


def _trade_text(trade: Trade, viewer_id: int) -> str:
    role = "Sotuvchi" if viewer_id == trade.seller_id else "Xaridor"
    return (
        f"🆔 Savdo #{trade.id} — {_STATUS_LABEL[trade.status]}\n"
        f"👤 Rolingiz: <b>{role}</b>\n"
        f"📦 {format_crypto(trade.amount)} {trade.asset}\n"
        f"💵 Jami: ${format_fiat(trade.fiat_total)}\n"
        f"🏷 Komissiya: {format_crypto(trade.fee)} {trade.asset}"
    )


# --- take an offer ---------------------------------------------------------
@router.callback_query(OfferCB.filter(F.action == "take"))
async def take_offer_start(
    callback: CallbackQuery, callback_data: OfferCB, state: FSMContext
) -> None:
    await state.set_state(TakeOffer.waiting_amount)
    await state.update_data(offer_id=callback_data.offer_id)
    await callback.message.answer(
        "Qancha miqdorda savdo qilmoqchisiz? (masalan: <code>0.1</code>)"
    )
    await callback.answer()


@router.message(TakeOffer.waiting_amount)
async def take_offer_amount(
    message: Message, state: FSMContext, escrow: EscrowService
) -> None:
    try:
        amount = parse_positive_crypto(message.text or "")
    except InvalidAmount as exc:
        await message.answer(str(exc))
        return
    data = await state.get_data()
    try:
        trade = await escrow.take_offer(
            offer_id=data["offer_id"],
            taker_id=message.from_user.id,
            amount=amount,
        )
    except InsufficientFunds as exc:
        await message.answer(
            f"❌ Eskrou uchun mablag‘ yetarli emas: {exc}"
        )
        await state.clear()
        return
    except TradeError as exc:
        await message.answer(f"❌ {exc}")
        await state.clear()
        return
    await state.clear()

    await message.answer(
        "🤝 Savdo boshlandi!\n\n" + _trade_text(trade, message.from_user.id),
        reply_markup=trade_actions(trade, message.from_user.id),
    )
    # Notify the counterparty.
    other = (
        trade.seller_id
        if message.from_user.id == trade.buyer_id
        else trade.buyer_id
    )
    try:
        await message.bot.send_message(
            other,
            "🔔 Yangi savdo!\n\n" + _trade_text(trade, other),
            reply_markup=trade_actions(trade, other),
        )
    except Exception:  # noqa: BLE001 - counterparty may not have started the bot
        pass


# --- my trades -------------------------------------------------------------
@router.message(Command("trades"))
async def cmd_trades(message: Message, session: AsyncSession) -> None:
    uid = message.from_user.id
    result = await session.scalars(
        select(Trade)
        .where(or_(Trade.seller_id == uid, Trade.buyer_id == uid))
        .order_by(Trade.created_at.desc())
        .limit(15)
    )
    trades = list(result)
    if not trades:
        await message.answer("Sizda savdolar yo‘q. /market dan boshlang.")
        return
    for trade in trades:
        kb = (
            trade_actions(trade, uid)
            if trade.status in (TradeStatus.ESCROW_LOCKED, TradeStatus.FIAT_PAID)
            else None
        )
        await message.answer(_trade_text(trade, uid), reply_markup=kb)


# --- lifecycle actions -----------------------------------------------------
async def _notify(bot, user_id: int, trade: Trade, text: str) -> None:
    try:
        await bot.send_message(
            user_id,
            f"{text}\n\n" + _trade_text(trade, user_id),
            reply_markup=trade_actions(trade, user_id),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(TradeCB.filter(F.action == "paid"))
async def trade_paid(
    callback: CallbackQuery, callback_data: TradeCB, escrow: EscrowService
) -> None:
    try:
        trade = await escrow.mark_fiat_paid(
            callback_data.trade_id, callback.from_user.id
        )
    except TradeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("To‘lov belgilandi ✅")
    await callback.message.edit_text(
        "💸 To‘lov tasdiqlandi. Sotuvchi mablag‘ni chiqarishini kuting.\n\n"
        + _trade_text(trade, callback.from_user.id)
    )
    await _notify(
        callback.bot, trade.seller_id, trade,
        "🔔 Xaridor to‘lovni tasdiqladi — mablag‘ni chiqaring.",
    )


@router.callback_query(TradeCB.filter(F.action == "release"))
async def trade_release(
    callback: CallbackQuery, callback_data: TradeCB, escrow: EscrowService
) -> None:
    try:
        trade = await escrow.release(callback_data.trade_id, callback.from_user.id)
    except TradeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Mablag‘ chiqarildi ✅")
    await callback.message.edit_text(
        "✅ Savdo yakunlandi. Kripto xaridorga o‘tkazildi.\n\n"
        + _trade_text(trade, callback.from_user.id)
    )
    await _notify(
        callback.bot, trade.buyer_id, trade, "🎉 Kripto hamyoningizga tushdi!"
    )


@router.callback_query(TradeCB.filter(F.action == "cancel"))
async def trade_cancel(
    callback: CallbackQuery, callback_data: TradeCB, escrow: EscrowService
) -> None:
    try:
        trade = await escrow.cancel_trade(
            callback_data.trade_id, callback.from_user.id
        )
    except TradeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Bekor qilindi")
    await callback.message.edit_text(
        "❌ Savdo bekor qilindi. Eskroudagi kripto sotuvchiga qaytarildi.\n\n"
        + _trade_text(trade, callback.from_user.id)
    )
    other = (
        trade.seller_id
        if callback.from_user.id == trade.buyer_id
        else trade.buyer_id
    )
    await _notify(callback.bot, other, trade, "🔔 Savdo bekor qilindi.")


@router.callback_query(TradeCB.filter(F.action == "dispute"))
async def trade_dispute(
    callback: CallbackQuery, callback_data: TradeCB, escrow: EscrowService
) -> None:
    try:
        trade = await escrow.dispute(callback_data.trade_id, callback.from_user.id)
    except TradeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Nizo ochildi")
    await callback.message.edit_text(
        "⚠️ Nizo ochildi. Eskroudagi mablag‘ hal qilinmaguncha bloklangan.\n\n"
        + _trade_text(trade, callback.from_user.id)
    )
