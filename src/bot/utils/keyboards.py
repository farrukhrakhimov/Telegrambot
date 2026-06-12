from __future__ import annotations

import importlib
from typing import Any


def confirm_cancel_keyboard(action: str, user_id: int) -> Any:
    aiogram_types = importlib.import_module("aiogram.types")
    return aiogram_types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                aiogram_types.InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{action}:{user_id}"),
                aiogram_types.InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel:{action}:{user_id}"),
            ]
        ]
    )
