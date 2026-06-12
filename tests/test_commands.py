from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import asyncio

import pytest

from bot.config import Config
from bot.database import Database
from bot.handlers.commands import perform_ban, perform_mute, perform_unban, perform_warn


@dataclass
class FakeBot:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def ban_chat_member(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("ban_chat_member", args, kwargs))

    async def unban_chat_member(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("unban_chat_member", args, kwargs))

    async def restrict_chat_member(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("restrict_chat_member", args, kwargs))


@pytest.fixture
def db() -> Database:
    database = Database(":memory:")
    asyncio.run(database.connect())
    asyncio.run(database.init())
    try:
        yield database
    finally:
        asyncio.run(database.close())


def test_perform_ban_writes_to_database(db: Database) -> None:
    async def scenario() -> None:
        bot = FakeBot()
        await perform_ban(bot, db, -100, 42, "spam", 7)

        assert bot.calls[0][0] == "ban_chat_member"
        ban = await db.get_ban(-100, 42)
        assert ban is not None
        assert ban["reason"] == "spam"
        assert ban["banned_by"] == 7

    asyncio.run(scenario())


def test_perform_unban_removes_database_record(db: Database) -> None:
    async def scenario() -> None:
        bot = FakeBot()
        await db.add_ban(-100, 42, "spam", 7)
        await perform_unban(bot, db, -100, 42)

        assert bot.calls[0][0] == "unban_chat_member"
        assert await db.get_ban(-100, 42) is None

    asyncio.run(scenario())


def test_perform_mute_writes_to_database(db: Database) -> None:
    async def scenario() -> None:
        bot = FakeBot()
        await perform_mute(bot, db, -100, 42, 3600, "flood")

        assert bot.calls[0][0] == "restrict_chat_member"
        mute = await db.get_mute(-100, 42)
        assert mute is not None
        assert mute["reason"] == "flood"

    asyncio.run(scenario())


def test_warn_auto_mutes_and_auto_bans(db: Database) -> None:
    async def scenario() -> None:
        bot = FakeBot()
        config = Config(
            BOT_TOKEN="token",
            WARN_LIMIT=3,
            BAN_LIMIT=5,
            AUTO_MUTE_DURATION="1h",
            CAPTCHA_ENABLED=False,
        )

        for index in range(1, 4):
            count = await perform_warn(bot, db, config, -100, 42, f"warn {index}", 7)
        assert count == 3
        assert await db.get_mute(-100, 42) is not None

        await perform_warn(bot, db, config, -100, 42, "warn 4", 7)
        count = await perform_warn(bot, db, config, -100, 42, "warn 5", 7)
        assert count == 5
        assert await db.get_ban(-100, 42) is not None
        assert await db.count_warnings(-100, 42) == 0

    asyncio.run(scenario())
