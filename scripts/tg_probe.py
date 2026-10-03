"""Диагностика Telegram: получить chat_id и проверить валидность url-кнопок.

Запускать при ОСТАНОВЛЕННОМ боте (иначе getUpdates даёт 409 Conflict).
    python scripts/tg_probe.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

TOKEN = settings.bot_token


def api(method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if params is None:
        req = url
    else:
        data = json.dumps(params).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:
            return {"ok": False, "description": str(exc)}


def main() -> None:
    updates = api("getUpdates", {"limit": 30, "timeout": 0})
    if not updates.get("ok"):
        print("getUpdates FAIL:", updates)
        return
    items = updates.get("result", [])
    print("pending updates:", len(items))
    chat_id = None
    for up in items:
        payload = (
            up.get("message")
            or up.get("edited_message")
            or up.get("inline_query")
            or up.get("callback_query")
        )
        if payload and "from" in payload:
            chat_id = payload["from"]["id"]
            print("  update:", [k for k in up if k != "update_id"],
                  "-> from", chat_id, payload["from"].get("username"))
    if chat_id is None:
        print("Нет апдейтов с 'from' — напиши боту что-нибудь и повтори")
        return

    urls = [
        f"https://t.me/{settings.bot_username}/{settings.webapp_short_name}?startapp=TEST"
        if settings.webapp_short_name else None,
        f"https://t.me/{settings.bot_username}?startapp=TEST",
        f"https://t.me/{settings.bot_username}",
    ]
    print("--- probing (chat_id=%s) ---" % chat_id)
    for url in urls:
        if not url:
            continue
        res = api("sendMessage", {
            "chat_id": chat_id,
            "text": f"probe: {url}",
            "reply_markup": {"inline_keyboard": [[{"text": "test", "url": url}]]},
        })
        status = "OK" if res.get("ok") else "FAIL: " + str(res.get("description"))
        print(f"  {status}  {url}")


if __name__ == "__main__":
    main()
