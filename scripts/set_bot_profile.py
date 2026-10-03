"""Задаёт описание бота в Telegram (setMyShortDescription / setMyDescription).

Запуск на сервере (там есть доступ к api.telegram.org):
    python scripts/set_bot_profile.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

SHORT = (
    "⚓ SeaBlitz — быстрая морская дуэль 5×5 на 1–2 минуты. "
    "Одновременные залпы, без долгих расстановок."
)

DESCRIPTION = (
    "⚓ SeaBlitz — морской блиц 5×5: дуэль за 1–2 минуты.\n\n"
    "Каждый раунд — 10 секунд: выбирай 3 клетки на поле соперника и жми «ОГОНЬ!». "
    "Залпы одновременные, поэтому нет преимущества первого хода. Побеждаешь, "
    "когда потопишь весь флот врага быстрее соперника.\n\n"
    "• Быстрый бой со случайным соперником\n"
    "• Вызов другу прямо в чате — карточка «Принять бой»\n"
    "• Если оба флота тонут одновременно — «Золотой раунд»\n\n"
    "Заходи и играй одной кнопкой!"
)


def api(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{settings.bot_token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read())


def main() -> None:
    print("short:", api("setMyShortDescription", {"short_description": SHORT}))
    print("description:", api("setMyDescription", {"description": DESCRIPTION}))


if __name__ == "__main__":
    main()
