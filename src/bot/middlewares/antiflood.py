from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from bot.logging import logger

from bot.config import Config
from bot.database import Database
from bot.texts import TEXTS
from bot.utils.moderation import duration_to_until, format_timedelta


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, flood_limit: int = 5, flood_window_seconds: int = 10, mute_seconds: int = 600) -> None:
        self.flood_limit = flood_limit
        self.flood_window_seconds = flood_window_seconds
        self.mute_seconds = mute_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.from_user is None or event.text is None:
            return await handler(event, data)

        db: Database | None = data.get("db")
        config: Config | None = data.get("config")
        if db is None or config is None:
            return await handler(event, data)

        state = await db.register_activity(
            event.chat.id,
            event.from_user.id,
            "text",
            flood_window_seconds=self.flood_window_seconds,
            flood_limit=self.flood_limit,
            content_limit=config.sticker_gif_flood_limit,
        )
        if state.is_flood:
            until = duration_to_until(self.mute_seconds)
            reason = "flood"
            await event.bot.restrict_chat_member(event.chat.id, event.from_user.id, until_date=until)
            await db.add_mute(event.chat.id, event.from_user.id, until, reason)
            logger.info("AntiFlood muted user={} chat={} seconds={}", event.from_user.id, event.chat.id, self.mute_seconds)
            await event.answer(
                TEXTS["auto_mute"].format(
                    user=event.from_user.full_name,
                    duration=format_timedelta(self.mute_seconds),
                    reason=reason,
                )
            )
            return None

        return await handler(event, data)
