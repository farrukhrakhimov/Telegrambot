from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .utils.moderation import parse_duration


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _parse_int_tuple(value: str | tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if isinstance(value, str):
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    return tuple(value)


def _parse_str_tuple(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().casefold() for item in value.split(",") if item.strip())
    return tuple(item.casefold() for item in value)


@dataclass
class _FallbackConfig:
    bot_token: str
    superadmin_ids: tuple[int, ...] = field(default_factory=tuple)
    warn_limit: int = 3
    ban_limit: int = 5
    auto_mute_duration: str = "1h"
    forbidden_words: tuple[str, ...] = field(default_factory=tuple)
    welcome_message: str = "Welcome {name}!"
    rules: str = "1. Be respectful\n2. No spam"
    links_allowed: bool = False
    captcha_enabled: bool = True
    delete_service_messages: bool = True
    mixed_script_filter_enabled: bool = False
    sticker_gif_flood_limit: int = 3
    log_level: str = "INFO"
    database_path: Path = Path("data/bot.db")

    def __init__(self, **kwargs: Any) -> None:
        env = os.environ
        self.bot_token = str(kwargs.get("BOT_TOKEN", kwargs.get("bot_token", env.get("BOT_TOKEN", ""))))
        self.superadmin_ids = _parse_int_tuple(kwargs.get("SUPERADMIN_IDS", kwargs.get("superadmin_ids", env.get("SUPERADMIN_IDS", ""))))
        self.warn_limit = int(kwargs.get("WARN_LIMIT", kwargs.get("warn_limit", env.get("WARN_LIMIT", 3))))
        self.ban_limit = int(kwargs.get("BAN_LIMIT", kwargs.get("ban_limit", env.get("BAN_LIMIT", 5))))
        self.auto_mute_duration = str(kwargs.get("AUTO_MUTE_DURATION", kwargs.get("auto_mute_duration", env.get("AUTO_MUTE_DURATION", "1h"))))
        self.forbidden_words = _parse_str_tuple(kwargs.get("FORBIDDEN_WORDS", kwargs.get("forbidden_words", env.get("FORBIDDEN_WORDS", ""))))
        self.welcome_message = str(kwargs.get("WELCOME_MESSAGE", kwargs.get("welcome_message", env.get("WELCOME_MESSAGE", "Welcome {name}!"))))
        self.rules = str(kwargs.get("RULES", kwargs.get("rules", env.get("RULES", "1. Be respectful\n2. No spam"))))
        self.links_allowed = _parse_bool(kwargs.get("LINKS_ALLOWED", kwargs.get("links_allowed", env.get("LINKS_ALLOWED", "false"))))
        self.captcha_enabled = _parse_bool(kwargs.get("CAPTCHA_ENABLED", kwargs.get("captcha_enabled", env.get("CAPTCHA_ENABLED", "true"))))
        self.delete_service_messages = _parse_bool(
            kwargs.get("DELETE_SERVICE_MESSAGES", kwargs.get("delete_service_messages", env.get("DELETE_SERVICE_MESSAGES", "true")))
        )
        self.mixed_script_filter_enabled = _parse_bool(
            kwargs.get(
                "MIXED_SCRIPT_FILTER_ENABLED",
                kwargs.get("mixed_script_filter_enabled", env.get("MIXED_SCRIPT_FILTER_ENABLED", "false")),
            )
        )
        self.sticker_gif_flood_limit = int(
            kwargs.get("STICKER_GIF_FLOOD_LIMIT", kwargs.get("sticker_gif_flood_limit", env.get("STICKER_GIF_FLOOD_LIMIT", 3)))
        )
        self.log_level = str(kwargs.get("LOG_LEVEL", kwargs.get("log_level", env.get("LOG_LEVEL", "INFO"))))
        self.database_path = Path(kwargs.get("DATABASE_PATH", kwargs.get("database_path", env.get("DATABASE_PATH", "data/bot.db"))))
        if not self.bot_token:
            raise ValueError("BOT_TOKEN is required")
        if self.warn_limit <= 0 or self.ban_limit <= 0 or self.sticker_gif_flood_limit <= 0:
            raise ValueError("limits must be positive")

    @property
    def auto_mute_seconds(self) -> int:
        duration = parse_duration(self.auto_mute_duration)
        if duration is None:
            raise ValueError("AUTO_MUTE_DURATION cannot be permanent")
        return duration


if importlib.util.find_spec("pydantic_settings") is not None:
    pydantic = importlib.import_module("pydantic")
    pydantic_settings = importlib.import_module("pydantic_settings")

    class Config(pydantic_settings.BaseSettings):  # type: ignore[name-defined]
        model_config = pydantic_settings.SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

        bot_token: str = pydantic.Field(..., alias="BOT_TOKEN")
        superadmin_ids: tuple[int, ...] = pydantic.Field(default=(), alias="SUPERADMIN_IDS")
        warn_limit: int = pydantic.Field(default=3, alias="WARN_LIMIT")
        ban_limit: int = pydantic.Field(default=5, alias="BAN_LIMIT")
        auto_mute_duration: str = pydantic.Field(default="1h", alias="AUTO_MUTE_DURATION")
        forbidden_words: tuple[str, ...] = pydantic.Field(default=(), alias="FORBIDDEN_WORDS")
        welcome_message: str = pydantic.Field(default="Welcome {name}!", alias="WELCOME_MESSAGE")
        rules: str = pydantic.Field(default="1. Be respectful\n2. No spam", alias="RULES")
        links_allowed: bool = pydantic.Field(default=False, alias="LINKS_ALLOWED")
        captcha_enabled: bool = pydantic.Field(default=True, alias="CAPTCHA_ENABLED")
        delete_service_messages: bool = pydantic.Field(default=True, alias="DELETE_SERVICE_MESSAGES")
        mixed_script_filter_enabled: bool = pydantic.Field(default=False, alias="MIXED_SCRIPT_FILTER_ENABLED")
        sticker_gif_flood_limit: int = pydantic.Field(default=3, alias="STICKER_GIF_FLOOD_LIMIT")
        log_level: str = pydantic.Field(default="INFO", alias="LOG_LEVEL")
        database_path: Path = pydantic.Field(default=Path("data/bot.db"), alias="DATABASE_PATH")

        @pydantic.field_validator("superadmin_ids", mode="before")
        @classmethod
        def parse_superadmins(cls, value: str | tuple[int, ...] | list[int]) -> tuple[int, ...] | list[int]:
            if isinstance(value, str):
                return _parse_int_tuple(value)
            return value

        @pydantic.field_validator("forbidden_words", mode="before")
        @classmethod
        def parse_forbidden_words(cls, value: str | tuple[str, ...] | list[str]) -> tuple[str, ...] | list[str]:
            if isinstance(value, str):
                return _parse_str_tuple(value)
            return value

        @pydantic.field_validator("warn_limit", "ban_limit", "sticker_gif_flood_limit")
        @classmethod
        def validate_positive_int(cls, value: int) -> int:
            if value <= 0:
                raise ValueError("value must be positive")
            return value

        @property
        def auto_mute_seconds(self) -> int:
            duration = parse_duration(self.auto_mute_duration)
            if duration is None:
                raise ValueError("AUTO_MUTE_DURATION cannot be permanent")
            return duration

else:
    Config = _FallbackConfig


@lru_cache(maxsize=1)
def load_config() -> Config:
    return Config()
