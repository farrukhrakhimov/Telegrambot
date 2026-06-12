# Telegram Admin Bot

Production-ready Telegram bot for group administration and moderation. The bot can help admins ban, kick, mute, warn users, publish rules, greet new members, run a math captcha, delete spam, block links, detect flood and keep moderation history in SQLite.

> Telegram bots cannot promote themselves. Add the bot to your group manually and grant admin permissions for deleting messages, banning users and restricting members.

## Features

- Admin commands: `/ban`, `/unban`, `/kick`, `/mute`, `/unmute`, `/warn`, `/unwarn`, `/warns`, `/rules`, `/setrulesо`, `/adminlist`, `/help`.
- Persistent SQLite storage with `aiosqlite` for warnings, mutes, bans, user activity, per-chat settings and captcha challenges.
- Config via `.env` using `pydantic-settings`.
- Loguru structured action logging.
- Admin-only middleware that short-circuits non-admin users.
- Inline confirm/cancel buttons for destructive `/ban` and `/kick` actions.
- Auto-moderation for forbidden words, external links, flood, sticker/GIF flood, mixed Arabic/Cyrillic text and caps-lock spam.
- Welcome messages with `{name}` and `{chat}` placeholders.
- Optional math captcha with 60-second timeout.

## Project structure

```text
telegram_admin_bot/
├── src/
│   └── bot/
│       ├── __main__.py
│       ├── config.py
│       ├── database.py
│       ├── texts.py
│       ├── middlewares/
│       │   ├── admin_check.py
│       │   └── antiflood.py
│       ├── filters/
│       │   └── is_admin.py
│       ├── handlers/
│       │   ├── commands.py
│       │   ├── welcome.py
│       │   └── automod.py
│       └── utils/
│           ├── moderation.py
│           └── keyboards.py
├── tests/
│   ├── test_commands.py
│   ├── test_automod.py
│   └── test_db.py
├── .env.example
├── pyproject.toml
└── README.md
```

## Setup

### 1. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather).
2. Run `/newbot`.
3. Copy the token.
4. Add the bot to your group.
5. Promote it to administrator and allow:
   - delete messages;
   - ban users;
   - restrict users.

### 2. Install Python dependencies

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . pytest pytest-asyncio
```

Alternatively:

```bash
python -m pip install -r requirements.txt
```

### 3. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and set at least `BOT_TOKEN` and `SUPERADMIN_IDS`.

### 4. Run the bot

```bash
python -m bot
```

## `.env` configuration

| Key | Required | Default | Description |
| --- | --- | --- | --- |
| `BOT_TOKEN` | yes | empty | Token from BotFather. |
| `SUPERADMIN_IDS` | no | empty | Comma-separated Telegram user IDs allowed to use `/setrulesо` and future bot settings. |
| `WARN_LIMIT` | no | `3` | Warnings before automatic mute. |
| `BAN_LIMIT` | no | `5` | Warnings before automatic ban. |
| `AUTO_MUTE_DURATION` | no | `1h` | Automatic mute duration after `WARN_LIMIT`: `10m`, `2h`, `1d`, `7d`. |
| `FORBIDDEN_WORDS` | no | empty | Comma-separated words deleted by auto-moderation. |
| `WELCOME_MESSAGE` | no | `Welcome {name}!` | New member greeting. Supports `{name}` and `{chat}`. |
| `RULES` | no | `1. Be respectful\n2. No spam` | Rules shown by `/rules`. |
| `LINKS_ALLOWED` | no | `false` | If `false`, external links are deleted. |
| `CAPTCHA_ENABLED` | no | `true` | If `true`, new users must solve a math captcha within 60 seconds. |
| `DELETE_SERVICE_MESSAGES` | no | `true` | Delete join/leave service messages. |
| `MIXED_SCRIPT_FILTER_ENABLED` | no | `false` | Delete and warn messages that mix Arabic and Cyrillic scripts. |
| `STICKER_GIF_FLOOD_LIMIT` | no | `3` | Delete sticker/GIF flood after this many repeated items in a row. |
| `LOG_LEVEL` | no | `INFO` | Loguru logging level. |
| `DATABASE_PATH` | no | `data/bot.db` | SQLite database file path. Use `:memory:` only for tests. |

## Command reference

All moderation commands require the caller to be a chat administrator. Commands accept either a reply to the target user or a `user_id` argument. `@username` is accepted only when Telegram exposes enough information; if it cannot be resolved, use a reply or numeric ID.

| Command | Description | Example |
| --- | --- | --- |
| `/ban [reason]` | Permanent ban, writes to DB, requires inline confirmation. | Reply: `/ban spam` or `/ban 123 spam` |
| `/unban` | Unban user and remove DB ban record. | `/unban 123` |
| `/kick` | Kick user without permanent ban, requires inline confirmation. | Reply: `/kick` |
| `/mute [duration] [reason]` | Restrict messages. Duration: `10m`, `2h`, `1d`, `7d`, `permanent`. | Reply: `/mute 2h spam` |
| `/unmute` | Remove restrictions and DB mute record. | `/unmute 123` |
| `/warn [reason]` | Add warning. Auto-mute after `WARN_LIMIT`, auto-ban after `BAN_LIMIT`. | Reply: `/warn caps` |
| `/unwarn` | Remove the latest warning. | Reply: `/unwarn` |
| `/warns` | Show warning list. | Reply: `/warns` |
| `/rules` | Show current group rules. | `/rules` |
| `/setrulesо <text>` | Update per-chat rules. Superadmin only. | `/setrulesо 1. Be kind` |
| `/adminlist` | List current Telegram chat admins. | `/adminlist` |
| `/help` | Show command list. | `/help` |

## Auto-moderation behavior

1. Forbidden words: delete message and add a warning.
2. External links: delete message if `LINKS_ALLOWED=false`.
3. Flood: more than 5 messages in 10 seconds automatically mutes for 10 minutes.
4. Sticker/GIF flood: repeated sticker/GIF messages are deleted after `STICKER_GIF_FLOOD_LIMIT`.
5. Arabic/Cyrillic mixed-script filter: optional, controlled by `MIXED_SCRIPT_FILTER_ENABLED`.
6. Caps lock spam: messages longer than 20 characters with more than 80% uppercase letters trigger a warning.

## Database

The bot initializes these tables automatically:

- `warnings(id, chat_id, user_id, reason, issued_at, issued_by)`
- `mutes(id, chat_id, user_id, until, reason)`
- `bans(id, chat_id, user_id, reason, banned_at, banned_by)`
- `user_activity(chat_id, user_id, last_seen, message_count)` plus content-kind counters for sticker/GIF flood
- `settings(chat_id, key, value)`
- `captcha_challenges(chat_id, user_id, answer, expires_at)`

All SQL is isolated in `src/bot/database.py`.

## Deploy to a VPS

### 1. Copy project

```bash
git clone <your-repo-url> telegram_admin_bot
cd telegram_admin_bot
```

### 2. Install runtime

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

### 3. Configure environment

```bash
cp .env.example .env
nano .env
```

### 4. Create a systemd service

Create `/etc/systemd/system/telegram-admin-bot.service`:

```ini
[Unit]
Description=Telegram Admin Bot
After=network.target

[Service]
WorkingDirectory=/opt/telegram_admin_bot
EnvironmentFile=/opt/telegram_admin_bot/.env
ExecStart=/opt/telegram_admin_bot/.venv/bin/python -m bot
Restart=always
RestartSec=5
User=telegrambot
Group=telegrambot

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-admin-bot
sudo systemctl start telegram-admin-bot
sudo journalctl -u telegram-admin-bot -f
```

## Development checks

```bash
python -m compileall src
pytest -v --tb=short
```
