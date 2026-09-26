"""Inline keyboards and callback-data factories."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Offer, OfferSide, Trade, TradeStatus


class AssetCB(CallbackData, prefix="asset"):
    flow: str  # deposit | withdraw | offer
    asset: str


class OfferCB(CallbackData, prefix="offer"):
    action: str  # take | cancel
    offer_id: int


class TradeCB(CallbackData, prefix="trade"):
    action: str  # paid | release | cancel | dispute
    trade_id: int


def asset_picker(assets: list[str], flow: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for asset in assets:
        builder.button(
            text=asset, callback_data=AssetCB(flow=flow, asset=asset).pack()
        )
    builder.adjust(3)
    return builder.as_markup()


def offer_row(offer: Offer, *, is_maker: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_maker:
        builder.button(
            text="🗑 Taklifni bekor qilish",
            callback_data=OfferCB(action="cancel", offer_id=offer.id).pack(),
        )
    else:
        verb = "Sotib olish" if offer.side is OfferSide.SELL else "Sotish"
        builder.button(
            text=f"🤝 {verb}",
            callback_data=OfferCB(action="take", offer_id=offer.id).pack(),
        )
    return builder.as_markup()


def trade_actions(trade: Trade, viewer_id: int) -> InlineKeyboardMarkup:
    """Buttons available to this viewer for the trade's current state."""
    builder = InlineKeyboardBuilder()
    is_buyer = viewer_id == trade.buyer_id
    is_seller = viewer_id == trade.seller_id

    if trade.status == TradeStatus.ESCROW_LOCKED:
        if is_buyer:
            builder.button(
                text="💸 To‘lovni tasdiqladim",
                callback_data=TradeCB(action="paid", trade_id=trade.id).pack(),
            )
        builder.button(
            text="❌ Bekor qilish",
            callback_data=TradeCB(action="cancel", trade_id=trade.id).pack(),
        )
    elif trade.status == TradeStatus.FIAT_PAID and is_seller:
        builder.button(
            text="✅ Mablag‘ni chiqarish",
            callback_data=TradeCB(action="release", trade_id=trade.id).pack(),
        )

    if trade.status in (TradeStatus.ESCROW_LOCKED, TradeStatus.FIAT_PAID):
        builder.button(
            text="⚠️ Nizo ochish",
            callback_data=TradeCB(action="dispute", trade_id=trade.id).pack(),
        )
    builder.adjust(1)
    return builder.as_markup()
