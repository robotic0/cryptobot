"""Aggregates all feature routers (common/cancel first)."""
from aiogram import Router

from app.handlers import common, market, start, trades, wallet


def get_routers() -> list[Router]:
    return [
        common.router,
        start.router,
        wallet.router,
        market.router,
        trades.router,
    ]


__all__ = ["get_routers"]
