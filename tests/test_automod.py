from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import asyncio

import pytest

from bot.config import Config
from bot.database import Database
from bot.handlers.automod import analyze_message, apply_automod
from bot.utils.moderation import contains_external_link, has_mixed_arabic_cyrillic, is_caps_spam


@dataclass
class FakeUser:
    id: int = 42
    full_name: str = "Target User"


@dataclass
class FakeChat:
    id: int = -100
    title: str = "Test Chat"


@dataclass
class FakeBot:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def restrict_chat_member(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("restrict_chat_member", args, kwargs))


@dataclass
class FakeMessage:
    text: str | None
    from_user: FakeUser = field(default_factory=FakeUser)
    chat: FakeChat = field(default_factory=FakeChat)
    bot: FakeBot = field(default_factory=FakeBot)
    caption: str | None = None
    animation: object | None = None
    sticker: object | None = None
    deleted: bool = False
    answers: list[str] = field(default_factory=list)

    async def delete(self) -> None:
        self.deleted = True

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


@pytest.fixture
def db() -> Database:
    database = Database(":memory:")
    asyncio.run(database.connect())
    asyncio.run(database.init())
    try:
        yield database
    finally:
        asyncio.run(database.close())


def test_automod_text_detectors() -> None:
    assert contains_external_link("see https://example.com") is True
    assert has_mixed_arabic_cyrillic("тест سلام") is True
    assert is_caps_spam("THIS MESSAGE IS DEFINITELY TOO LOUD") is True


def test_forbidden_words_delete_and_warn(db: Database) -> None:
    async def scenario() -> None:
        config = Config(BOT_TOKEN="token", FORBIDDEN_WORDS="spam", CAPTCHA_ENABLED=False)
        message = FakeMessage("Buy SPAM now")

        decision = await apply_automod(message, config, db)

        assert decision is not None
        assert decision.delete is True
        assert decision.warn is True
        assert message.deleted is True
        assert await db.count_warnings(-100, 42) == 1

    asyncio.run(scenario())


def test_links_are_deleted_when_disabled(db: Database) -> None:
    async def scenario() -> None:
        config = Config(BOT_TOKEN="token", LINKS_ALLOWED=False, CAPTCHA_ENABLED=False)
        message = FakeMessage("visit https://example.com")

        decision = await analyze_message(message, config, db)

        assert decision is not None
        assert decision.delete is True
        assert decision.reason == "external links"

    asyncio.run(scenario())


def test_flood_detection_mutes_user(db: Database) -> None:
    async def scenario() -> None:
        config = Config(BOT_TOKEN="token", CAPTCHA_ENABLED=False)
        message = FakeMessage("hello")

        for _ in range(6):
            decision = await apply_automod(message, config, db)

        assert decision is not None
        assert decision.mute_seconds == 600
        assert message.bot.calls[-1][0] == "restrict_chat_member"
        assert await db.get_mute(-100, 42) is not None

    asyncio.run(scenario())
