from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
from typing import Any

from bot.logging import logger

from bot.config import Config
from bot.database import Database
from bot.texts import TEXTS
from bot.utils.moderation import (
    contains_external_link,
    contains_forbidden_word,
    duration_to_until,
    format_timedelta,
    has_mixed_arabic_cyrillic,
    is_caps_spam,
)

@dataclass(frozen=True)
class AutomodDecision:
    delete: bool
    warn: bool
    mute_seconds: int | None
    reason: str


async def analyze_message(message: Any, config: Config, db: Database) -> AutomodDecision | None:
    if message.from_user is None:
        return None

    content_kind = "animation" if message.animation else "sticker" if message.sticker else "text"
    state = await db.register_activity(
        message.chat.id,
        message.from_user.id,
        content_kind,
        content_limit=config.sticker_gif_flood_limit,
    )

    text = message.text or message.caption or ""
    if contains_forbidden_word(text, config.forbidden_words):
        return AutomodDecision(delete=True, warn=True, mute_seconds=None, reason="forbidden words")
    if not config.links_allowed and contains_external_link(text):
        return AutomodDecision(delete=True, warn=False, mute_seconds=None, reason="external links")
    if state.is_flood:
        return AutomodDecision(delete=False, warn=False, mute_seconds=600, reason="flood")
    if state.is_content_flood:
        return AutomodDecision(delete=True, warn=False, mute_seconds=None, reason="sticker/gif flood")
    if config.mixed_script_filter_enabled and has_mixed_arabic_cyrillic(text):
        return AutomodDecision(delete=True, warn=True, mute_seconds=None, reason="mixed Arabic/Cyrillic text")
    if is_caps_spam(text):
        return AutomodDecision(delete=False, warn=True, mute_seconds=None, reason="caps lock spam")
    return None


async def apply_automod(message: Any, config: Config, db: Database) -> AutomodDecision | None:
    decision = await analyze_message(message, config, db)
    if decision is None or message.from_user is None:
        return decision

    if decision.delete:
        await message.delete()
        await message.answer(TEXTS["automod_deleted"].format(reason=decision.reason))

    if decision.warn:
        count = await db.add_warning(message.chat.id, message.from_user.id, decision.reason, 0)
        logger.info("automod warn target={} chat={} count={} reason={}", message.from_user.id, message.chat.id, count, decision.reason)

    if decision.mute_seconds is not None:
        until = duration_to_until(decision.mute_seconds)
        await message.bot.restrict_chat_member(
            message.chat.id,
            message.from_user.id,
            permissions=_chat_permissions(can_send_messages=False),
            until_date=until,
        )
        await db.add_mute(message.chat.id, message.from_user.id, until, decision.reason)
        await message.answer(
            TEXTS["auto_mute"].format(
                user=message.from_user.full_name,
                duration=format_timedelta(decision.mute_seconds),
                reason=decision.reason,
            )
        )
        logger.info("automod mute target={} chat={} seconds={}", message.from_user.id, message.chat.id, decision.mute_seconds)

    return decision


async def automod_message(message: Any, config: Config, db: Database) -> None:
    try:
        await apply_automod(message, config, db)
    except Exception as exc:
        logger.exception("Automod failed: chat={} error={}", message.chat.id, exc)
        await message.answer(TEXTS["error"])


def _chat_permissions(**kwargs: Any) -> Any:
    if importlib.util.find_spec("aiogram") is None:
        return kwargs
    aiogram_types = importlib.import_module("aiogram.types")
    return aiogram_types.ChatPermissions(**kwargs)


def create_router() -> Any:
    aiogram = importlib.import_module("aiogram")
    router = aiogram.Router(name="automod")
    router.message()(automod_message)
    return router
