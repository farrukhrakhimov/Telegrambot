from __future__ import annotations

import importlib
import importlib.util
import logging
from typing import Any


class _StdLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("telegram_admin_bot")

    def _format(self, message: str, *args: Any) -> str:
        return message.format(*args) if args else message

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(self._format(message, *args), **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(self._format(message, *args), **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.exception(self._format(message, *args), **kwargs)

    def add(self, *args: Any, **kwargs: Any) -> None:
        logging.basicConfig(level=kwargs.get("level", "INFO"))

    def remove(self, *args: Any, **kwargs: Any) -> None:
        return None


if importlib.util.find_spec("loguru") is not None:
    logger = importlib.import_module("loguru").logger
else:
    logger = _StdLogger()
