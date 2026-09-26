"""/start, /help and /price (live market rates)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.rates import RateService
from app.utils.money import format_fiat

router = Router(name="start")

WELCOME = (
    "👛 <b>CryptoBot</b> — ko‘p valyutali hamyon va P2P savdo maydonchasi.\n\n"
    "• 💰 /wallet — balanslaringiz\n"
    "• 📥 /deposit — hisobni to‘ldirish (simulyatsiya)\n"
    "• 📤 /withdraw — yechib olish\n"
    "• 🏪 /market — P2P takliflar\n"
    "• 🟢 /sell · 🔵 /buy — taklif joylash\n"
    "• 📊 /price — joriy kurslar\n"
    "• 🔐 /setpin — tranzaksiya PIN kodi\n\n"
    "⚠️ <i>Bu ta’limiy loyiha: hamyon ichki simulyatsiya qilingan ledgerda "
    "ishlaydi, haqiqiy blokcheyn kalitlari saqlanmaydi.</i>"
)

HELP = (
    "<b>CryptoBot qo‘llanmasi</b>\n\n"
    "<b>Hamyon</b>\n"
    "/wallet — balanslar · /deposit — to‘ldirish · /withdraw — yechish\n\n"
    "<b>P2P savdo</b>\n"
    "/market — ochiq takliflar\n"
    "/sell — sotish taklifi · /buy — sotib olish taklifi\n"
    "/myoffers — mening takliflarim · /trades — savdolarim\n\n"
    "<b>Eskrou oqimi</b>\n"
    "1. Xaridor taklifni qabul qiladi → sotuvchi kripto eskrouga bloklanadi\n"
    "2. Xaridor fiat to‘lovni yuboradi va «To‘lovni tasdiqladim» bosadi\n"
    "3. Sotuvchi to‘lovni oladi va «Mablag‘ni chiqarish» bosadi\n\n"
    "<b>Xavfsizlik</b>\n"
    "/setpin — yechish/chiqarish uchun PIN o‘rnatish"
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("price"))
async def cmd_price(message: Message, rates: RateService) -> None:
    prices = await rates.all_prices()
    if not prices:
        await message.answer(
            "Kurslarni hozircha olib bo‘lmadi. Birozdan so‘ng qayta urinib ko‘ring."
        )
        return
    lines = [
        f"• <b>{asset}</b>: ${format_fiat(price)}"
        for asset, price in prices.items()
    ]
    await message.answer("📊 <b>Joriy kurslar (USD)</b>\n\n" + "\n".join(lines))
