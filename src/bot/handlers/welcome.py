from __future__ import annotations

import asyncio
import importlib
import random
from typing import Any

from bot.logging import logger

from bot.config import Config
from bot.database import Database
from bot.texts import TEXTS

async def create_math_challenge(message: Any, db: Database, user_id: int, name: str) -> None:
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    await db.create_captcha(message.chat.id, user_id, str(a + b), ttl_seconds=60)
    await message.answer(TEXTS["captcha"].format(name=name, a=a, b=b))

    async def kick_if_unanswered() -> None:
        await asyncio.sleep(60)
        try:
            is_valid = await db.verify_captcha(message.chat.id, user_id, "__expired__")
            if not is_valid:
                await message.bot.ban_chat_member(message.chat.id, user_id)
                await message.bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
                await db.delete_captcha(message.chat.id, user_id)
                logger.info("captcha kick target={} chat={}", user_id, message.chat.id)
        except Exception as exc:
            logger.exception("Captcha timeout failed: chat={} user={} error={}", message.chat.id, user_id, exc)

    asyncio.create_task(kick_if_unanswered())


async def welcome_new_members(message: Any, config: Config, db: Database) -> None:
    try:
        if config.delete_service_messages:
            await message.delete()
        for member in message.new_chat_members or []:
            text = config.welcome_message.format(name=member.full_name, chat=message.chat.title or "чат")
            await message.answer(text)
            if config.captcha_enabled and not member.is_bot:
                await create_math_challenge(message, db, member.id, member.full_name)
            logger.info("welcome user={} chat={}", member.id, message.chat.id)
    except Exception as exc:
        logger.exception("Welcome handler failed: chat={} error={}", message.chat.id, exc)
        await message.answer(TEXTS["error"])


async def delete_left_service_message(message: Any, config: Config) -> None:
    try:
        if config.delete_service_messages:
            await message.delete()
    except Exception as exc:
        logger.exception("Failed to delete left-chat service message: chat={} error={}", message.chat.id, exc)


async def captcha_answer(message: Any, db: Database) -> None:
    try:
        if message.from_user is None or message.text is None:
            return
        if await db.verify_captcha(message.chat.id, message.from_user.id, message.text):
            await message.answer(TEXTS["captcha_ok"])
            logger.info("captcha passed target={} chat={}", message.from_user.id, message.chat.id)
    except Exception as exc:
        logger.exception("Captcha answer failed: chat={} error={}", message.chat.id, exc)


def create_router() -> Any:
    aiogram = importlib.import_module("aiogram")
    router = aiogram.Router(name="welcome")
    router.message(aiogram.F.new_chat_members)(welcome_new_members)
    router.message(aiogram.F.left_chat_member)(delete_left_service_message)
    router.message(aiogram.F.text)(captcha_answer)
    return router
