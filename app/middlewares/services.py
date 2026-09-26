"""Middleware that opens a DB session per update and injects services."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.base import Database
from app.database.models import User
from app.services.escrow import EscrowService
from app.services.security import SecurityService
from app.services.wallet import WalletService


class ServicesMiddleware(BaseMiddleware):
    def __init__(self, database: Database, fee_rate: Decimal) -> None:
        self._db = database
        self._fee_rate = fee_rate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._db.session() as session:
            data["session"] = session
            data["wallet"] = WalletService(session)
            data["escrow"] = EscrowService(session, self._fee_rate)
            data["security"] = SecurityService(session)

            # Ensure a User row exists for the actor.
            user = data.get("event_from_user")
            if user is not None and await session.get(User, user.id) is None:
                session.add(User(id=user.id))

            result = await handler(event, data)
            await session.commit()
            return result
