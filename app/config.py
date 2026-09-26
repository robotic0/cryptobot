"""Application configuration loaded from environment variables."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from environs import Env


@dataclass(slots=True)
class Config:
    token: str
    database_url: str
    fee_rate: Decimal
    rate_ttl: int


def load_config(path: str | None = None) -> Config:
    env = Env()
    env.read_env(path)
    return Config(
        token=env.str("BOT_TOKEN"),
        database_url=env.str("DATABASE_URL", "sqlite+aiosqlite:///cryptobot.db"),
        fee_rate=Decimal(env.str("FEE_RATE", "0.01")),  # 1% platform fee
        rate_ttl=env.int("RATE_TTL_SECONDS", 60),
    )
