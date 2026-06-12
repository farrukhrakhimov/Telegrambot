from __future__ import annotations

from datetime import datetime, timezone

import asyncio

import pytest

from bot.database import Database


@pytest.fixture
def db() -> Database:
    database = Database(":memory:")
    asyncio.run(database.connect())
    asyncio.run(database.init())
    try:
        yield database
    finally:
        asyncio.run(database.close())


def test_warning_crud_round_trip(db: Database) -> None:
    async def scenario() -> None:
        count = await db.add_warning(-100, 42, "spam", 7)
        assert count == 1

        warnings = await db.list_warnings(-100, 42)
        assert len(warnings) == 1
        assert warnings[0].reason == "spam"
        assert warnings[0].issued_by == 7

        removed = await db.remove_last_warning(-100, 42)
        assert removed is True
        assert await db.count_warnings(-100, 42) == 0

    asyncio.run(scenario())


def test_mute_and_ban_round_trips(db: Database) -> None:
    async def scenario() -> None:
        until = datetime.now(timezone.utc)
        await db.add_mute(-100, 42, until, "flood")
        mute = await db.get_mute(-100, 42)
        assert mute is not None
        assert mute["reason"] == "flood"

        await db.remove_mute(-100, 42)
        assert await db.get_mute(-100, 42) is None

        await db.add_ban(-100, 42, "spam", 7)
        ban = await db.get_ban(-100, 42)
        assert ban is not None
        assert ban["banned_by"] == 7

        await db.remove_ban(-100, 42)
        assert await db.get_ban(-100, 42) is None

    asyncio.run(scenario())


def test_settings_activity_and_captcha(db: Database) -> None:
    async def scenario() -> None:
        await db.set_setting(-100, "rules", "Be kind")
        assert await db.get_setting(-100, "rules") == "Be kind"

        for _ in range(6):
            state = await db.register_activity(-100, 42, "text")
        assert state.is_flood is True

        await db.create_captcha(-100, 42, "12")
        assert await db.verify_captcha(-100, 42, "12") is True
        assert await db.verify_captcha(-100, 42, "12") is False

    asyncio.run(scenario())
