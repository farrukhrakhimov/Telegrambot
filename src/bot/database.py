from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import importlib
import importlib.util
import sqlite3



UTC = timezone.utc


class _AsyncSqliteFallback:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self.row_factory: Any = None

    async def close(self) -> None:
        self._conn.close()

    async def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        self._conn.row_factory = self.row_factory
        return self._conn.execute(sql, parameters)

    async def executescript(self, sql_script: str) -> Any:
        self._conn.row_factory = self.row_factory
        return self._conn.executescript(sql_script)

    async def execute_fetchall(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[Any]:
        self._conn.row_factory = self.row_factory
        cursor = self._conn.execute(sql, parameters)
        return cursor.fetchall()

    async def commit(self) -> None:
        self._conn.commit()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class WarningRecord:
    id: int
    chat_id: int
    user_id: int
    reason: str
    issued_at: str
    issued_by: int


@dataclass(frozen=True)
class ActivityState:
    message_count: int
    is_flood: bool
    content_count: int
    is_content_flood: bool


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._connection: Any | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        if importlib.util.find_spec("aiosqlite") is not None:
            aiosqlite = importlib.import_module("aiosqlite")
            self._connection = await aiosqlite.connect(self.path)
            self._connection.row_factory = aiosqlite.Row
            await self._connection.execute("PRAGMA foreign_keys = ON")
        else:
            self._connection = _AsyncSqliteFallback(self.path)
            self._connection.row_factory = sqlite3.Row
            await self._connection.execute("PRAGMA foreign_keys = ON")

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> Any:
        if self._connection is None:
            raise RuntimeError("Database is not connected")
        return self._connection

    async def init(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                issued_by INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                until TEXT,
                reason TEXT NOT NULL,
                UNIQUE(chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                banned_at TEXT NOT NULL,
                banned_by INTEGER NOT NULL,
                UNIQUE(chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS user_activity (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                last_seen TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                last_content_kind TEXT NOT NULL DEFAULT '',
                content_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY(chat_id, key)
            );

            CREATE TABLE IF NOT EXISTS captcha_challenges (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                answer TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY(chat_id, user_id)
            );
            """
        )
        await self.conn.commit()

    async def add_warning(self, chat_id: int, user_id: int, reason: str, issued_by: int) -> int:
        await self.conn.execute(
            "INSERT INTO warnings(chat_id, user_id, reason, issued_at, issued_by) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, reason, utc_now_iso(), issued_by),
        )
        await self.conn.commit()
        return await self.count_warnings(chat_id, user_id)

    async def remove_last_warning(self, chat_id: int, user_id: int) -> bool:
        row = await self.conn.execute_fetchall(
            "SELECT id FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id, user_id),
        )
        if not row:
            return False
        await self.conn.execute("DELETE FROM warnings WHERE id = ?", (row[0]["id"],))
        await self.conn.commit()
        return True

    async def list_warnings(self, chat_id: int, user_id: int) -> list[WarningRecord]:
        rows = await self.conn.execute_fetchall(
            "SELECT id, chat_id, user_id, reason, issued_at, issued_by FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY id",
            (chat_id, user_id),
        )
        return [WarningRecord(**dict(row)) for row in rows]

    async def count_warnings(self, chat_id: int, user_id: int) -> int:
        rows = await self.conn.execute_fetchall(
            "SELECT COUNT(*) AS count FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return int(rows[0]["count"])

    async def clear_warnings(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute("DELETE FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await self.conn.commit()

    async def add_mute(self, chat_id: int, user_id: int, until: datetime | None, reason: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO mutes(chat_id, user_id, until, reason) VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET until = excluded.until, reason = excluded.reason
            """,
            (chat_id, user_id, until.isoformat() if until else None, reason),
        )
        await self.conn.commit()

    async def remove_mute(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute("DELETE FROM mutes WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await self.conn.commit()

    async def get_mute(self, chat_id: int, user_id: int) -> dict[str, object] | None:
        rows = await self.conn.execute_fetchall(
            "SELECT id, chat_id, user_id, until, reason FROM mutes WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return dict(rows[0]) if rows else None

    async def add_ban(self, chat_id: int, user_id: int, reason: str, banned_by: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO bans(chat_id, user_id, reason, banned_at, banned_by) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET reason = excluded.reason, banned_at = excluded.banned_at, banned_by = excluded.banned_by
            """,
            (chat_id, user_id, reason, utc_now_iso(), banned_by),
        )
        await self.conn.commit()

    async def remove_ban(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute("DELETE FROM bans WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await self.conn.commit()

    async def get_ban(self, chat_id: int, user_id: int) -> dict[str, object] | None:
        rows = await self.conn.execute_fetchall(
            "SELECT id, chat_id, user_id, reason, banned_at, banned_by FROM bans WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return dict(rows[0]) if rows else None

    async def register_activity(
        self,
        chat_id: int,
        user_id: int,
        content_kind: str,
        flood_window_seconds: int = 10,
        flood_limit: int = 5,
        content_limit: int = 3,
    ) -> ActivityState:
        now = datetime.now(UTC)
        rows = await self.conn.execute_fetchall(
            "SELECT last_seen, message_count, last_content_kind, content_count FROM user_activity WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        if rows:
            row = rows[0]
            last_seen = datetime.fromisoformat(row["last_seen"])
            in_window = now - last_seen <= timedelta(seconds=flood_window_seconds)
            message_count = int(row["message_count"]) + 1 if in_window else 1
            previous_kind = str(row["last_content_kind"])
            content_count = int(row["content_count"]) + 1 if previous_kind == content_kind and content_kind in {"sticker", "animation"} else 1
            await self.conn.execute(
                """
                UPDATE user_activity
                SET last_seen = ?, message_count = ?, last_content_kind = ?, content_count = ?
                WHERE chat_id = ? AND user_id = ?
                """,
                (now.isoformat(), message_count, content_kind, content_count, chat_id, user_id),
            )
        else:
            message_count = 1
            content_count = 1
            await self.conn.execute(
                "INSERT INTO user_activity(chat_id, user_id, last_seen, message_count, last_content_kind, content_count) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, now.isoformat(), message_count, content_kind, content_count),
            )
        await self.conn.commit()
        return ActivityState(
            message_count=message_count,
            is_flood=message_count > flood_limit,
            content_count=content_count,
            is_content_flood=content_kind in {"sticker", "animation"} and content_count > content_limit,
        )

    async def set_setting(self, chat_id: int, key: str, value: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO settings(chat_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(chat_id, key) DO UPDATE SET value = excluded.value
            """,
            (chat_id, key, value),
        )
        await self.conn.commit()

    async def get_setting(self, chat_id: int, key: str) -> str | None:
        rows = await self.conn.execute_fetchall(
            "SELECT value FROM settings WHERE chat_id = ? AND key = ?",
            (chat_id, key),
        )
        return str(rows[0]["value"]) if rows else None

    async def create_captcha(self, chat_id: int, user_id: int, answer: str, ttl_seconds: int = 60) -> None:
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        await self.conn.execute(
            """
            INSERT INTO captcha_challenges(chat_id, user_id, answer, expires_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET answer = excluded.answer, expires_at = excluded.expires_at
            """,
            (chat_id, user_id, answer, expires_at.isoformat()),
        )
        await self.conn.commit()

    async def verify_captcha(self, chat_id: int, user_id: int, answer: str) -> bool:
        rows = await self.conn.execute_fetchall(
            "SELECT answer, expires_at FROM captcha_challenges WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        if not rows:
            return False
        row = rows[0]
        expires_at = datetime.fromisoformat(row["expires_at"])
        is_valid = datetime.now(UTC) <= expires_at and str(row["answer"]) == answer.strip()
        if is_valid:
            await self.delete_captcha(chat_id, user_id)
        return is_valid

    async def delete_captcha(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute("DELETE FROM captcha_challenges WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await self.conn.commit()
