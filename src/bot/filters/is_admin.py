from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import Message


ADMIN_STATUSES = {"administrator", "creator"}


class ChatAdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.from_user is None:
            return False
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return str(member.status) in ADMIN_STATUSES
