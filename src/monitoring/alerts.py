"""Simple Telegram alerting (optional)."""

from __future__ import annotations
from typing import Optional
from loguru import logger

from src.utils.config import AppConfig


class AlertService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.enabled = (
            config.monitoring.telegram.enabled
            and bool(config.monitoring.telegram.bot_token)
            and bool(config.monitoring.telegram.chat_id)
        )
        self._bot = None

        if self.enabled:
            try:
                from telegram import Bot
                self._bot = Bot(token=config.monitoring.telegram.bot_token)
                logger.info("Telegram alerts enabled")
            except Exception as e:
                logger.warning(f"Telegram init failed: {e}")
                self.enabled = False

    async def send(self, message: str) -> None:
        if not self.enabled or not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=self.config.monitoring.telegram.chat_id,
                text=message,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def info(self, msg: str) -> None:
        await self.send(f"ℹ️ {msg}")

    async def warning(self, msg: str) -> None:
        await self.send(f"⚠️ {msg}")

    async def critical(self, msg: str) -> None:
        await self.send(f"🚨 {msg}")
