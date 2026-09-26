"""P2P marketplace: browse, create and cancel offers."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database.models import OfferSide
from app.keyboards.inline import AssetCB, OfferCB, asset_picker, offer_row
from app.services.escrow import EscrowService, TradeError
from app.services.rates import RateService
from app.states import CreateOffer
from app.utils.money import (
    InvalidAmount,
    format_crypto,
    format_fiat,
    parse_positive_crypto,
    to_decimal,
)

router = Router(name="market")


def _offer_text(offer, viewer_id: int) -> str:
    side = "🟢 SOTADI" if offer.side is OfferSide.SELL else "🔵 SOTIB OLADI"
    mine = " · <i>(sizniki)</i>" if offer.maker_id == viewer_id else ""
    return (
        f"{side} <b>{offer.asset}</b>{mine}\n"
        f"💵 Narx: ${format_fiat(offer.price_usd)} / {offer.asset}\n"
        f"📦 Qolgan: {format_crypto(offer.remaining)} {offer.asset}\n"
        f"💳 To‘lov: {offer.payment_method}\n"
        f"🆔 #{offer.id}"
    )


@router.message(Command("market"))
async def cmd_market(message: Message, escrow: EscrowService) -> None:
    offers = await escrow.open_offers()
    if not offers:
        await message.answer(
            "Hozircha ochiq takliflar yo‘q. /sell yoki /buy bilan birinchi bo‘ling!"
        )
        return
    await message.answer(f"🏪 <b>Ochiq takliflar ({len(offers)})</b>")
    for offer in offers[:20]:
        is_maker = offer.maker_id == message.from_user.id
        await message.answer(
            _offer_text(offer, message.from_user.id),
            reply_markup=offer_row(offer, is_maker=is_maker),
        )


@router.message(Command("myoffers"))
async def cmd_myoffers(message: Message, escrow: EscrowService) -> None:
    offers = [
        o
        for o in await escrow.open_offers()
        if o.maker_id == message.from_user.id
    ]
    if not offers:
        await message.answer("Sizda ochiq takliflar yo‘q.")
        return
    for offer in offers:
        await message.answer(
            _offer_text(offer, message.from_user.id),
            reply_markup=offer_row(offer, is_maker=True),
        )


# --- create offer ----------------------------------------------------------
@router.message(Command("sell"))
async def cmd_sell(message: Message, state: FSMContext, rates: RateService) -> None:
    await _begin_offer(message, state, rates, OfferSide.SELL)


@router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext, rates: RateService) -> None:
    await _begin_offer(message, state, rates, OfferSide.BUY)


async def _begin_offer(
    message: Message, state: FSMContext, rates: RateService, side: OfferSide
) -> None:
    await state.set_state(CreateOffer.waiting_asset)
    await state.update_data(side=side.value)
    verb = "sotish" if side is OfferSide.SELL else "sotib olish"
    await message.answer(
        f"Qaysi aktivni {verb} taklifini yaratasiz?",
        reply_markup=asset_picker(rates.supported, flow="offer"),
    )


@router.callback_query(CreateOffer.waiting_asset, AssetCB.filter(F.flow == "offer"))
async def offer_asset(
    callback: CallbackQuery, callback_data: AssetCB, state: FSMContext
) -> None:
    await state.update_data(asset=callback_data.asset)
    await state.set_state(CreateOffer.waiting_amount)
    await callback.message.edit_text(
        f"<b>{callback_data.asset}</b> — miqdorni yuboring. Masalan: <code>0.25</code>"
    )
    await callback.answer()


@router.message(CreateOffer.waiting_amount)
async def offer_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_positive_crypto(message.text or "")
    except InvalidAmount as exc:
        await message.answer(str(exc))
        return
    await state.update_data(amount=str(amount))
    await state.set_state(CreateOffer.waiting_price)
    await message.answer(
        "💵 1 birlik uchun narxni USD da yuboring. Masalan: <code>60000</code>"
    )


@router.message(CreateOffer.waiting_price)
async def offer_price(message: Message, state: FSMContext) -> None:
    try:
        price = to_decimal(message.text or "")
    except InvalidAmount as exc:
        await message.answer(str(exc))
        return
    if price <= 0:
        await message.answer("Narx noldan katta bo‘lishi kerak.")
        return
    await state.update_data(price=str(price))
    await state.set_state(CreateOffer.waiting_payment)
    await message.answer(
        "💳 To‘lov usulini yozing (masalan: <i>Bank kartasi, Payme, Naqd</i>):"
    )


@router.message(CreateOffer.waiting_payment)
async def offer_payment(
    message: Message, state: FSMContext, escrow: EscrowService
) -> None:
    payment = (message.text or "").strip()[:64]
    if not payment:
        await message.answer("To‘lov usulini yozing.")
        return
    data = await state.get_data()
    try:
        offer = await escrow.create_offer(
            maker_id=message.from_user.id,
            side=OfferSide(data["side"]),
            asset=data["asset"],
            amount=parse_positive_crypto(data["amount"]),
            price_usd=to_decimal(data["price"]),
            payment_method=payment,
        )
    except TradeError as exc:
        await message.answer(f"❌ {exc}")
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ Taklif joylandi! 🆔 #{offer.id}\n\n"
        + _offer_text(offer, message.from_user.id)
    )


@router.callback_query(OfferCB.filter(F.action == "cancel"))
async def cancel_offer(
    callback: CallbackQuery, callback_data: OfferCB, escrow: EscrowService
) -> None:
    try:
        await escrow.cancel_offer(callback_data.offer_id, callback.from_user.id)
    except TradeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Taklif bekor qilindi ✅")
    await callback.message.edit_text("🗑 Taklif bekor qilindi.")
