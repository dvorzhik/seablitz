"""Telegram-бот SeaBlitz: запуск Mini App и инлайн-вызовы на бой.

Запуск (long polling):
    python -m bot.main

Требуется BOT_TOKEN (+ BOT_USERNAME, WEBAPP_SHORT_NAME) в переменных окружения.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    WebAppInfo,
)

from app.config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("seablitz.bot")

dp = Dispatcher()
CODE_PREFIX_RE = re.compile(r"blitz[-:\s]*([A-Za-z0-9]{4})", re.IGNORECASE)
BARE_CODE_RE = re.compile(r"^[A-Za-z0-9]{4}$")


def candidate_urls(code: str = "") -> List[str]:
    """Возможные ссылки на Mini App: именованная (short name), затем главная."""
    username = settings.bot_username or "seablitz_bot"
    suffix = f"?startapp={code}" if code else ""
    raw = []
    if settings.webapp_short_name:
        raw.append(f"https://t.me/{username}/{settings.webapp_short_name}{suffix}")
    raw.append(f"https://t.me/{username}{suffix}")
    out: List[str] = []
    for url in raw:
        if url not in out:
            out.append(url)
    return out


def webapp_url(param: str = "") -> str:
    """Приоритетная ссылка на Mini App; с кодом комнаты в ``startapp``."""
    return candidate_urls(param)[0]


def extract_code(text: str) -> Optional[str]:
    """Достаёт код комнаты из текста инлайн-запроса.

    Поддерживает формат ``blitz-ABCD`` (его шлёт Mini App) и одиночный код
    ``ABCD``. Слово «blitz» само по себе кодом не считается.
    """
    text = (text or "").strip()
    match = CODE_PREFIX_RE.search(text)
    if match:
        return match.group(1).upper()
    tokens = text.split()
    if len(tokens) == 1 and BARE_CODE_RE.match(tokens[0]):
        return tokens[0].upper()
    return None


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚓ Играть", web_app=WebAppInfo(url=webapp_url()))]
        ]
    )
    username = settings.bot_username or "seablitz_bot"
    await message.answer(
        "⚓ <b>SeaBlitz</b> — морская дуэль 5×5 за 1–2 минуты.\n\n"
        "Нажми «Играть», чтобы войти. Друга можно вызвать в любом чате: "
        f"набери <code>@{username}</code> и отправь карточку вызова.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


def _build_article(
    code: Optional[str], url: str, with_button: bool
) -> InlineQueryResultArticle:
    if code:
        title = "⚔️ Морской блиц — вызов на бой"
        text = (
            "⚔️ <b>Вызов на морскую дуэль!</b>\n"
            f"Код комнаты: <code>{code}</code>\nЖми «Принять бой»."
        )
        button_text = "Принять бой ⚔️"
    else:
        title = "⚓ Морской блиц — играть"
        text = "⚓ <b>SeaBlitz</b> — морская дуэль 5×5. Жми «Играть»."
        button_text = "Играть ⚓"

    reply_markup = None
    if with_button:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=url)]]
        )
    else:
        text += f"\n\n{url}"

    return InlineQueryResultArticle(
        id="seablitz-duel",
        title=title,
        description="Отправить карточку вызова в чат",
        input_message_content=InputTextMessageContent(
            message_text=text, parse_mode="HTML"
        ),
        reply_markup=reply_markup,
    )


@dp.inline_query()
async def on_inline(query: InlineQuery) -> None:
    code = extract_code(query.query)
    urls = candidate_urls(code or "")

    # Пробуем кнопки с разными формами ссылки; Telegram может одну отвергнуть.
    for url in urls:
        try:
            await query.answer(
                [_build_article(code, url, with_button=True)],
                cache_time=0,
                is_personal=True,
            )
            return
        except TelegramBadRequest as exc:
            log.warning("inline button url rejected (%s): %s", url, exc)

    # Последний шанс — карточка со ссылкой текстом, без кнопки.
    await query.answer(
        [_build_article(code, urls[-1], with_button=False)],
        cache_time=0,
        is_personal=True,
    )


async def main() -> None:
    if not settings.bot_token:
        raise SystemExit("Не задан BOT_TOKEN — см. .env.example")
    bot = Bot(token=settings.bot_token)
    log.info("SeaBlitz bot started (username=%s)", settings.bot_username or "?")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
