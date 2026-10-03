"""Настройки SeaBlitz из переменных окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # .env подхватывается и при локальном запуске (на сервере — systemd EnvironmentFile)
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv необязателен
    pass


@dataclass(frozen=True)
class Settings:
    """Конфигурация приложения и бота."""

    bot_token: str = os.getenv("BOT_TOKEN", "")
    bot_username: str = os.getenv("BOT_USERNAME", "")
    # Short name «named» Mini App из BotFather (/newapp). Пусто — используем
    # Mini App по кнопке меню (ссылка https://t.me/<bot>?startapp=<code>).
    webapp_short_name: str = os.getenv("WEBAPP_SHORT_NAME", "")
    base_url: str = os.getenv("BASE_URL", "")


settings = Settings()

