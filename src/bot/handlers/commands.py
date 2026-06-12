from __future__ import annotations

from collections.abc import Awaitable, Callable
import importlib
import importlib.util
from typing import Any

from bot.logging import logger

from bot.config import Config
from bot.database import Database, WarningRecord
from bot.texts import TEXTS
from bot.utils.keyboards import confirm_cancel_keyboard
from bot.utils.moderation import (
    command_args,
    duration_to_until,
    format_timedelta,
    parse_target_from_args,
    reason_without_target,
    split_duration_and_reason,
)



async def _safe(message: Any, action: Callable[[], Awaitable[None]]) -> None:
    try:
        await action()
    except Exception as exc:
        logger.exception("Handler failed: chat={} user={} error={}", message.chat.id, getattr(message.from_user, "id", None), exc)
        await message.answer(TEXTS["error"])


def _target_from_reply(message: Any) -> Any | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None


async def _resolve_target(message: Any) -> tuple[int | None, str, str]:
    reply_user = _target_from_reply(message)
    if reply_user is not None:
        return reply_user.id, reply_user.full_name, command_args(message.text)

    args = command_args(message.text)
    parsed = parse_target_from_args(args)
    if parsed is None:
        return None, "", args
    if parsed.user_id is None:
        return None, parsed.display, args
    return parsed.user_id, parsed.display, reason_without_target(args)


async def perform_ban(bot: Any, db: Database, chat_id: int, user_id: int, reason: str, actor_id: int) -> None:
    await bot.ban_chat_member(chat_id, user_id)
    await db.add_ban(chat_id, user_id, reason, actor_id)
    logger.info("ban actor={} target={} chat={} reason={}", actor_id, user_id, chat_id, reason)


async def perform_unban(bot: Any, db: Database, chat_id: int, user_id: int) -> None:
    await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    await db.remove_ban(chat_id, user_id)
    logger.info("unban target={} chat={}", user_id, chat_id)


async def perform_kick(bot: Any, chat_id: int, user_id: int, actor_id: int) -> None:
    await bot.ban_chat_member(chat_id, user_id)
    await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    logger.info("kick actor={} target={} chat={}", actor_id, user_id, chat_id)


async def perform_mute(bot: Any, db: Database, chat_id: int, user_id: int, seconds: int | None, reason: str) -> None:
    until = duration_to_until(seconds)
    await bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=_chat_permissions(can_send_messages=False),
        until_date=until,
    )
    await db.add_mute(chat_id, user_id, until, reason)
    logger.info("mute target={} chat={} seconds={} reason={}", user_id, chat_id, seconds, reason)


async def perform_unmute(bot: Any, db: Database, chat_id: int, user_id: int) -> None:
    await bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=_chat_permissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )
    await db.remove_mute(chat_id, user_id)
    logger.info("unmute target={} chat={}", user_id, chat_id)


async def perform_warn(bot: Any, db: Database, config: Config, chat_id: int, user_id: int, reason: str, actor_id: int) -> int:
    count = await db.add_warning(chat_id, user_id, reason, actor_id)
    logger.info("warn actor={} target={} chat={} count={} reason={}", actor_id, user_id, chat_id, count, reason)
    if count >= config.ban_limit:
        await perform_ban(bot, db, chat_id, user_id, "warning limit reached", actor_id)
        await db.clear_warnings(chat_id, user_id)
    elif count >= config.warn_limit:
        await perform_mute(bot, db, chat_id, user_id, config.auto_mute_seconds, "warning limit reached")
    return count


def format_warnings(user: str, warnings: list[WarningRecord]) -> str:
    if not warnings:
        return TEXTS["no_warns"].format(user=user)
    lines = [TEXTS["warns_header"].format(user=user)]
    for index, warning in enumerate(warnings, start=1):
        lines.append(f"{index}. {warning.reason} — admin {warning.issued_by}, {warning.issued_at}")
    return "\n".join(lines)


async def help_command(message: Any) -> None:
    await _safe(message, lambda: message.answer(TEXTS["help"]))


async def rules_command(message: Any, config: Config, db: Database) -> None:
    async def action() -> None:
        rules = await db.get_setting(message.chat.id, "rules") or config.rules
        await message.answer(rules)

    await _safe(message, action)


async def set_rules_command(message: Any, config: Config, db: Database) -> None:
    async def action() -> None:
        if message.from_user is None or message.from_user.id not in config.superadmin_ids:
            await message.answer(TEXTS["superadmin_only"])
            return
        rules = command_args(message.text)
        if not rules:
            await message.answer("Передайте текст правил после команды.")
            return
        await db.set_setting(message.chat.id, "rules", rules)
        logger.info("rules updated actor={} chat={}", message.from_user.id, message.chat.id)
        await message.answer(TEXTS["rules_updated"])

    await _safe(message, action)


async def ban_command(message: Any) -> None:
    async def action() -> None:
        user_id, user_display, reason = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        await message.answer(
            TEXTS["confirm_action"].format(action="ban", user=user_display),
            reply_markup=confirm_cancel_keyboard("ban", user_id),
        )

    await _safe(message, action)


async def kick_command(message: Any) -> None:
    async def action() -> None:
        user_id, user_display, _reason = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        await message.answer(
            TEXTS["confirm_action"].format(action="kick", user=user_display),
            reply_markup=confirm_cancel_keyboard("kick", user_id),
        )

    await _safe(message, action)


async def confirm_destructive(callback: Any, db: Database) -> None:
    try:
        if callback.message is None or callback.from_user is None or callback.data is None:
            return
        _prefix, action, raw_user_id = callback.data.split(":", 2)
        user_id = int(raw_user_id)
        chat_id = callback.message.chat.id
        if action == "ban":
            await perform_ban(callback.bot, db, chat_id, user_id, "confirmed by admin", callback.from_user.id)
        elif action == "kick":
            await perform_kick(callback.bot, chat_id, user_id, callback.from_user.id)
        await callback.message.edit_text(TEXTS["confirmed"])
        await callback.answer()
    except Exception as exc:
        logger.exception("Confirm callback failed: error={}", exc)
        await callback.answer(TEXTS["error"], show_alert=True)


async def cancel_destructive(callback: Any) -> None:
    try:
        if callback.message is not None:
            await callback.message.edit_text(TEXTS["cancelled"])
        await callback.answer()
    except Exception as exc:
        logger.exception("Cancel callback failed: error={}", exc)
        await callback.answer(TEXTS["error"], show_alert=True)


async def unban_command(message: Any, db: Database) -> None:
    async def action() -> None:
        user_id, user_display, _reason = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        await perform_unban(message.bot, db, message.chat.id, user_id)
        await message.answer(TEXTS["unban_done"].format(user=user_display))

    await _safe(message, action)


async def mute_command(message: Any, db: Database) -> None:
    async def action() -> None:
        user_id, user_display, args = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        try:
            seconds, reason = split_duration_and_reason(args, "1h")
        except ValueError:
            await message.answer(TEXTS["invalid_duration"])
            return
        await perform_mute(message.bot, db, message.chat.id, user_id, seconds, reason)
        await message.answer(TEXTS["mute_done"].format(user=user_display, duration=format_timedelta(seconds), reason=reason))

    await _safe(message, action)


async def unmute_command(message: Any, db: Database) -> None:
    async def action() -> None:
        user_id, user_display, _reason = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        await perform_unmute(message.bot, db, message.chat.id, user_id)
        await message.answer(TEXTS["unmute_done"].format(user=user_display))

    await _safe(message, action)


async def warn_command(message: Any, config: Config, db: Database) -> None:
    async def action() -> None:
        if message.from_user is None:
            await message.answer(TEXTS["admin_only"])
            return
        user_id, user_display, reason = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        reason = reason or "без указания причины"
        count = await perform_warn(message.bot, db, config, message.chat.id, user_id, reason, message.from_user.id)
        if count >= config.ban_limit:
            await message.answer(TEXTS["auto_ban"].format(user=user_display))
        else:
            await message.answer(TEXTS["warn_done"].format(user=user_display, count=count, ban_limit=config.ban_limit, reason=reason))

    await _safe(message, action)


async def unwarn_command(message: Any, db: Database) -> None:
    async def action() -> None:
        user_id, user_display, _reason = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        removed = await db.remove_last_warning(message.chat.id, user_id)
        await message.answer(TEXTS["unwarn_done"].format(user=user_display) if removed else TEXTS["no_warns"].format(user=user_display))

    await _safe(message, action)


async def warns_command(message: Any, db: Database) -> None:
    async def action() -> None:
        user_id, user_display, _reason = await _resolve_target(message)
        if user_id is None:
            await message.answer(TEXTS["target_required"] if not user_display else TEXTS["target_unresolvable"])
            return
        warning_list = await db.list_warnings(message.chat.id, user_id)
        await message.answer(format_warnings(user_display, warning_list))

    await _safe(message, action)


async def adminlist_command(message: Any) -> None:
    async def action() -> None:
        admins = await message.bot.get_chat_administrators(message.chat.id)
        lines = [TEXTS["adminlist_header"]]
        for admin in admins:
            lines.append(f"• {admin.user.full_name} ({admin.status})")
        await message.answer("\n".join(lines))

    await _safe(message, action)


def _chat_permissions(**kwargs: Any) -> Any:
    if importlib.util.find_spec("aiogram") is None:
        return kwargs
    aiogram_types = importlib.import_module("aiogram.types")
    return aiogram_types.ChatPermissions(**kwargs)


def create_router() -> Any:
    aiogram = importlib.import_module("aiogram")
    filters = importlib.import_module("aiogram.filters")
    router = aiogram.Router(name="commands")
    command = filters.Command
    router.message(command("help", "start"))(help_command)
    router.message(command("rules"))(rules_command)
    router.message(command("setrulesо"))(set_rules_command)
    router.message(command("ban"))(ban_command)
    router.message(command("kick"))(kick_command)
    router.callback_query(aiogram.F.data.startswith("confirm:"))(confirm_destructive)
    router.callback_query(aiogram.F.data.startswith("cancel:"))(cancel_destructive)
    router.message(command("unban"))(unban_command)
    router.message(command("mute"))(mute_command)
    router.message(command("unmute"))(unmute_command)
    router.message(command("warn"))(warn_command)
    router.message(command("unwarn"))(unwarn_command)
    router.message(command("warns"))(warns_command)
    router.message(command("adminlist"))(adminlist_command)
    return router
