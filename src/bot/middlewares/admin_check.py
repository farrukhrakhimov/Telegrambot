from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from bot.logging import logger

from bot.texts import TEXTS

ADMIN_COMMANDS = {
    "ban",
    "unban",
    "kick",
    "mute",
    "unmute",
    "warn",
    "unwarn",
    "warns",
    "setrulesо",
    "adminlist",
}
ADMIN_STATUSES = {"administrator", "creator"}


class AdminCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.text or not event.text.startswith("/"):
            return await handler(event, data)

        command = event.text.split(maxsplit=1)[0].split("@", 1)[0].lstrip("/").casefold()
        if command not in ADMIN_COMMANDS:
            return await handler(event, data)

        if event.from_user is None:
            await event.answer(TEXTS["admin_only"])
            return None

        member = await event.bot.get_chat_member(event.chat.id, event.from_user.id)
        if str(member.status) not in ADMIN_STATUSES:
            logger.warning(
                "Non-admin command attempt: user={} command={} chat={}",
                event.from_user.id,
                command,
                event.chat.id,
            )
            await event.answer(TEXTS["admin_only"])
            return None

        return await handler(event, data)
