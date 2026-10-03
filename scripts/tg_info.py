"""Разовые диагностические сведения о боте (запуск на сервере, где есть доступ к api.telegram.org)."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

T = settings.bot_token


def api(method: str) -> dict:
    url = f"https://api.telegram.org/bot{T}/{method}"
    try:
        return json.loads(urllib.request.urlopen(url, timeout=15).read())
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


for name in ("getMe", "getMyName", "getMyShortDescription", "getChatMenuButton", "getMyCommands"):
    print(f"--- {name} ---")
    print(json.dumps(api(name), ensure_ascii=False))
