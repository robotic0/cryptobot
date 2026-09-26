"""Wallet: balances, PIN, simulated deposit and withdrawal."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.inline import AssetCB, asset_picker
from app.services.rates import RateService
from app.services.security import SecurityService, is_valid_pin
from app.services.wallet import InsufficientFunds, WalletService
from app.states import Deposit, SetPin, Withdraw
from app.utils.money import InvalidAmount, format_crypto, parse_positive_crypto

router = Router(name="wallet")


@router.message(Command("wallet"))
async def cmd_wallet(
    message: Message, wallet: WalletService, rates: RateService
) -> None:
    balances = await wallet.all_balances(message.from_user.id)
    if not balances:
        await message.answer(
            "Hamyoningiz bo‘sh. /deposit orqali to‘ldiring."
        )
        return
    prices = await rates.all_prices()
    lines, total_usd = [], 0
    for b in balances:
        price = prices.get(b.asset)
        usd = f" (~${(b.available + b.locked) * price:,.2f})" if price else ""
        if price:
            total_usd += float((b.available + b.locked) * price)
        locked = f" · 🔒 {format_crypto(b.locked)}" if b.locked > 0 else ""
        lines.append(
            f"• <b>{b.asset}</b>: {format_crypto(b.available)}{locked}{usd}"
        )
    footer = f"\n\n💵 <b>Jami:</b> ~${total_usd:,.2f}" if total_usd else ""
    await message.answer("💰 <b>Hamyon</b>\n\n" + "\n".join(lines) + footer)


# --- PIN -------------------------------------------------------------------
@router.message(Command("setpin"))
async def cmd_setpin(message: Message, state: FSMContext) -> None:
    await state.set_state(SetPin.waiting_pin)
    await message.answer(
        "🔐 Yangi PIN kodni yuboring (4–8 raqam).\n"
        "Bekor qilish: /cancel"
    )


@router.message(SetPin.waiting_pin)
async def process_setpin(
    message: Message, state: FSMContext, security: SecurityService
) -> None:
    pin = (message.text or "").strip()
    if not is_valid_pin(pin):
        await message.answer("PIN 4–8 raqamdan iborat bo‘lishi kerak.")
        return
    await security.set_pin(message.from_user.id, pin)
    await state.clear()
    await message.answer("✅ PIN o‘rnatildi. Endi yechishlar PIN bilan himoyalangan.")


# --- deposit (simulated) ---------------------------------------------------
@router.message(Command("deposit"))
async def cmd_deposit(
    message: Message, state: FSMContext, rates: RateService
) -> None:
    await state.set_state(Deposit.waiting_asset)
    await message.answer(
        "📥 Qaysi aktivni to‘ldirasiz?",
        reply_markup=asset_picker(rates.supported, flow="deposit"),
    )


@router.callback_query(Deposit.waiting_asset, AssetCB.filter(F.flow == "deposit"))
async def deposit_asset(
    callback: CallbackQuery, callback_data: AssetCB, state: FSMContext
) -> None:
    await state.update_data(asset=callback_data.asset)
    await state.set_state(Deposit.waiting_amount)
    await callback.message.edit_text(
        f"<b>{callback_data.asset}</b> miqdorini yuboring "
        "(simulyatsiya — test uchun).\nMasalan: <code>0.5</code>"
    )
    await callback.answer()


@router.message(Deposit.waiting_amount)
async def deposit_amount(
    message: Message, state: FSMContext, wallet: WalletService
) -> None:
    try:
        amount = parse_positive_crypto(message.text or "")
    except InvalidAmount as exc:
        await message.answer(str(exc))
        return
    data = await state.get_data()
    asset = data["asset"]
    await wallet.credit(message.from_user.id, asset, amount)
    await state.clear()
    await message.answer(
        f"✅ Hamyonga <b>{format_crypto(amount)} {asset}</b> qo‘shildi (simulyatsiya)."
    )


# --- withdraw --------------------------------------------------------------
@router.message(Command("withdraw"))
async def cmd_withdraw(
    message: Message,
    state: FSMContext,
    security: SecurityService,
    rates: RateService,
) -> None:
    if not await security.has_pin(message.from_user.id):
        await message.answer("Avval /setpin orqali PIN o‘rnating.")
        return
    await state.set_state(Withdraw.waiting_asset)
    await message.answer(
        "📤 Qaysi aktivni yechasiz?",
        reply_markup=asset_picker(rates.supported, flow="withdraw"),
    )


@router.callback_query(Withdraw.waiting_asset, AssetCB.filter(F.flow == "withdraw"))
async def withdraw_asset(
    callback: CallbackQuery, callback_data: AssetCB, state: FSMContext
) -> None:
    await state.update_data(asset=callback_data.asset)
    await state.set_state(Withdraw.waiting_amount)
    await callback.message.edit_text(
        f"<b>{callback_data.asset}</b> — yechib olish miqdorini yuboring."
    )
    await callback.answer()


@router.message(Withdraw.waiting_amount)
async def withdraw_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_positive_crypto(message.text or "")
    except InvalidAmount as exc:
        await message.answer(str(exc))
        return
    await state.update_data(amount=str(amount))
    await state.set_state(Withdraw.waiting_address)
    await message.answer("Qabul qiluvchi manzilni yuboring:")


@router.message(Withdraw.waiting_address)
async def withdraw_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=(message.text or "").strip())
    await state.set_state(Withdraw.waiting_pin)
    await message.answer("🔐 Tasdiqlash uchun PIN kodni yuboring:")


@router.message(Withdraw.waiting_pin)
async def withdraw_pin(
    message: Message,
    state: FSMContext,
    wallet: WalletService,
    security: SecurityService,
) -> None:
    pin = (message.text or "").strip()
    if not await security.check_pin(message.from_user.id, pin):
        await message.answer("❌ Noto‘g‘ri PIN. Yechish bekor qilindi.")
        await state.clear()
        return
    data = await state.get_data()
    asset = data["asset"]
    amount = parse_positive_crypto(data["amount"])
    try:
        await wallet.debit(message.from_user.id, asset, amount)
    except InsufficientFunds as exc:
        await message.answer(f"❌ {exc}")
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ <b>{format_crypto(amount)} {asset}</b> yechildi (simulyatsiya) → "
        f"<code>{data['address']}</code>"
    )
