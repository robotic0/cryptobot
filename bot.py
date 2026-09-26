"""Entry point: wires together the bot, dispatcher, database and services."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import load_config
from app.database.base import Database
from app.handlers import get_routers
from app.middlewares import ServicesMiddleware
from app.services.rates import RateService
from app.utils import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    config = load_config()

    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    database = Database(config.database_url)
    await database.create_all()

    rates = RateService(ttl_seconds=config.rate_ttl)

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["rates"] = rates  # shared, cached rate service

    services_mw = ServicesMiddleware(database, config.fee_rate)
    dispatcher.message.middleware(services_mw)
    dispatcher.callback_query.middleware(services_mw)
    dispatcher.include_routers(*get_routers())

    logger.info("CryptoBot is starting (fee rate: %s)", config.fee_rate)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        await database.dispose()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("CryptoBot stopped")
