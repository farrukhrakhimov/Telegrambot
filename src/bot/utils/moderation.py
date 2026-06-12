from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_DURATION_RE = re.compile(r"^(?P<amount>\d+)(?P<unit>[mhd])$", re.IGNORECASE)
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.|t\.me/|telegram\.me/)[^\s]+")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_SECONDS_BY_UNIT = {"m": 60, "h": 60 * 60, "d": 24 * 60 * 60}


@dataclass(frozen=True)
class ParsedTarget:
    user_id: int | None
    username: str | None
    display: str


def parse_duration(value: str | None, default: str | None = None) -> int | None:
    raw_value = value or default
    if raw_value is None or raw_value.strip() == "":
        raise ValueError("Duration is required")

    normalized = raw_value.strip().casefold()
    if normalized == "permanent":
        return None

    match = _DURATION_RE.fullmatch(normalized)
    if not match:
        raise ValueError("Invalid duration")

    return int(match.group("amount")) * _SECONDS_BY_UNIT[match.group("unit").lower()]


def duration_to_until(seconds: int | None) -> datetime | None:
    if seconds is None:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def format_timedelta(seconds: int | None) -> str:
    if seconds is None:
        return "навсегда"
    if seconds < 60:
        return f"{seconds} сек."
    if seconds < 3600:
        return f"{seconds // 60} мин."
    if seconds < 86400:
        return f"{seconds // 3600} ч."
    return f"{seconds // 86400} д."


def split_duration_and_reason(args: str, default_duration: str) -> tuple[int | None, str]:
    parts = args.split(maxsplit=1)
    if not parts:
        return parse_duration(default_duration), "без указания причины"

    try:
        duration = parse_duration(parts[0])
    except ValueError:
        return parse_duration(default_duration), args.strip() or "без указания причины"

    reason = parts[1].strip() if len(parts) > 1 else "без указания причины"
    return duration, reason


def command_args(text: str | None) -> str:
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def parse_target_from_args(args: str) -> ParsedTarget | None:
    first = args.split(maxsplit=1)[0] if args else ""
    if not first:
        return None
    if first.startswith("@") and len(first) > 1:
        username = first[1:]
        return ParsedTarget(user_id=None, username=username, display=f"@{username}")
    try:
        user_id = int(first)
    except ValueError:
        return None
    if user_id <= 0:
        return None
    return ParsedTarget(user_id=user_id, username=None, display=str(user_id))


def reason_without_target(args: str) -> str:
    parts = args.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else "без указания причины"


def contains_forbidden_word(text: str | None, forbidden_words: tuple[str, ...]) -> bool:
    if not text:
        return False
    normalized = text.casefold()
    return any(word and word in normalized for word in forbidden_words)


def contains_external_link(text: str | None) -> bool:
    return bool(text and _URL_RE.search(text))


def has_mixed_arabic_cyrillic(text: str | None) -> bool:
    if not text:
        return False
    return bool(_CYRILLIC_RE.search(text) and _ARABIC_RE.search(text))


def uppercase_ratio(text: str | None) -> float:
    if not text:
        return 0.0
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for char in letters if char.isupper())
    return upper / len(letters)


def is_caps_spam(text: str | None, min_length: int = 20, threshold: float = 0.8) -> bool:
    if not text or len(text) <= min_length:
        return False
    return uppercase_ratio(text) > threshold
