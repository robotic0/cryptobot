"""Live market exchange rates via the CoinGecko public API (no key needed).

Results are cached for a short TTL to stay well within rate limits. The
network call is isolated here so the rest of the app — and the tests — can
work against an in-memory cache.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal

import aiohttp

logger = logging.getLogger(__name__)

# Telegram-friendly ticker -> CoinGecko id.
COIN_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "BNB": "binancecoin",
    "SOL": "solana",
    "TON": "the-open-network",
    "TRX": "tron",
    "XRP": "ripple",
}

_API = "https://api.coingecko.com/api/v3/simple/price"


class RateService:
    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, Decimal] = {}
        self._fetched_at: float = 0.0

    @property
    def supported(self) -> list[str]:
        return list(COIN_IDS)

    async def usd_price(self, asset: str) -> Decimal | None:
        prices = await self.all_prices()
        return prices.get(asset.upper())

    async def all_prices(self) -> dict[str, Decimal]:
        if self._cache and (time.monotonic() - self._fetched_at) < self._ttl:
            return self._cache
        try:
            self._cache = await self._fetch()
            self._fetched_at = time.monotonic()
        except Exception:  # noqa: BLE001 - never crash a handler on a rate outage
            logger.warning("Rate fetch failed; serving stale cache", exc_info=True)
        return self._cache

    async def _fetch(self) -> dict[str, Decimal]:
        ids = ",".join(COIN_IDS.values())
        params = {"ids": ids, "vs_currencies": "usd"}
        async with aiohttp.ClientSession() as session:
            async with session.get(_API, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()
        prices: dict[str, Decimal] = {}
        for ticker, coin_id in COIN_IDS.items():
            usd = data.get(coin_id, {}).get("usd")
            if usd is not None:
                prices[ticker] = Decimal(str(usd))
        return prices
