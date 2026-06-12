from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from bot.logging import logger

from bot.config import Config, load_config
from bot.database import Database
from bot.handlers import automod, commands, welcome
from bot.middlewares.admin_check import AdminCheckMiddleware


async def start_polling(config: Config) -> None:
    logger.remove()
    logger.add(sys.stderr, level=config.log_level)

    db = Database(config.database_path)
    await db.connect()
    await db.init()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(config=config, db=db)
    dp.message.middleware(AdminCheckMiddleware())
    dp.include_router(commands.create_router())
    dp.include_router(welcome.create_router())
    dp.include_router(automod.create_router())

    logger.info("Starting Telegram admin bot")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.close()
        logger.info("Telegram admin bot stopped")


def main() -> None:
    asyncio.run(start_polling(load_config()))


if __name__ == "__main__":
    main()
