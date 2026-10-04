"""SeaBlitz — FastAPI-приложение: WebSocket-комнаты и раздача Mini App."""
from __future__ import annotations

import base64
import html
import json
import secrets
import time
from pathlib import Path

from fastapi import (
    Body,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.net.rooms import Conn, RoomManager, clean_profile

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="SeaBlitz")
manager = RoomManager()


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Запрещаем эвристическое кеширование статики.

    Иначе браузер/Telegram могут надолго закешировать старый ``app.js`` и
    подгрузить его вместе с новым ``index.html`` — рассинхрон ломает экран
    результата. С ``no-cache`` клиент ревалидирует файлы по ETag.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "rooms": len(manager.rooms)}


# ---- Публичная картинка результата (OG-превью для Telegram) -----------------
# Telegram не на всех платформах даёт делиться картинкой из Mini App, поэтому
# клиент рисует PNG, загружает его сюда, а мы отдаём страницу с og:image —
# Telegram покажет превью с итогами боя в любом чате.
SHARE_TTL_SECONDS = 7 * 24 * 3600
SHARE_MAX_CHARS = 2_600_000  # ~2 МБ PNG в base64 (у nginx client_max_body_size 2m)
_shares: dict = {}


def _shares_cleanup() -> None:
    now = time.time()
    for token in [t for t, s in _shares.items() if now - s["ts"] > SHARE_TTL_SECONDS]:
        _shares.pop(token, None)


def _public_base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    if host:
        return f"{proto}://{host}"
    return (settings.base_url or "").rstrip("/")


@app.post("/api/share")
async def create_share(request: Request, payload: dict = Body(...)) -> dict:
    _shares_cleanup()
    image = str(payload.get("image") or "")
    if not image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="image_required")
    if len(image) > SHARE_MAX_CHARS:
        raise HTTPException(status_code=413, detail="too_big")
    token = secrets.token_urlsafe(8)
    _shares[token] = {
        "image": image,
        "title": str(payload.get("title") or "SeaBlitz")[:150],
        "text": str(payload.get("text") or "")[:300],
        "ts": time.time(),
    }
    return {"id": token, "url": f"{_public_base(request)}/s/{token}"}


@app.get("/s/{token}", response_class=HTMLResponse)
async def share_page(token: str, request: Request) -> HTMLResponse:
    _shares_cleanup()
    share = _shares.get(token)
    if share is None:
        raise HTTPException(status_code=404, detail="not_found")
    base = _public_base(request)
    img = f"{base}/s/{token}/card.png"
    title = html.escape(share["title"])
    text = html.escape(share["text"])
    play = html.escape(f"https://t.me/{settings.bot_username or 'seablitz_bot'}")
    return HTMLResponse(
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        "<meta property='og:type' content='website'>"
        f"<meta property='og:title' content='{title}'>"
        f"<meta property='og:description' content='{text}'>"
        f"<meta property='og:image' content='{img}'>"
        "<meta property='og:image:width' content='900'>"
        "<meta property='og:image:height' content='1560'>"
        "<meta name='twitter:card' content='summary_large_image'>"
        "<style>body{margin:0;background:#0b1e2d;color:#e8f1f8;"
        "font-family:-apple-system,Segoe UI,Roboto,sans-serif;text-align:center}"
        "img{max-width:100%;height:auto;display:block;margin:0 auto}"
        "a{display:inline-block;margin:18px;padding:14px 22px;background:#2ea6ff;"
        "color:#06222f;border-radius:12px;font-weight:700;text-decoration:none}</style>"
        "</head><body>"
        f"<img src='{img}' alt='Итоги боя'>"
        f"<div><a href='{play}'>⚓ Играть в SeaBlitz</a></div>"
        "</body></html>"
    )


@app.get("/s/{token}/card.png")
async def share_image(token: str) -> Response:
    share = _shares.get(token)
    if share is None:
        raise HTTPException(status_code=404, detail="not_found")
    _, _, b64 = share["image"].partition(",")
    try:
        data = base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=500, detail="bad_image")
    return Response(content=data, media_type="image/png")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    manager.conns[ws] = Conn(ws=ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                await handle_message(ws, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(ws)


async def handle_message(ws: WebSocket, msg: dict) -> None:
    conn = manager.conns.get(ws)
    if conn is None:
        return
    mtype = msg.get("type")

    if mtype == "join":
        if conn.room is not None:
            return
        conn.profile = clean_profile(msg.get("user"))
        code = str(msg.get("code") or "").strip().upper()[:8] or "LOBBY"
        await manager.join_by_code(ws, code)

    elif mtype == "quickmatch":
        if conn.room is not None:
            return
        conn.profile = clean_profile(msg.get("user"))
        await manager.enqueue(ws)

    elif mtype == "cancel":
        await manager.cancel_search(ws)

    elif mtype == "leave_room":
        await manager.leave_room(ws)

    elif mtype == "play_bot":
        if conn.room is not None:
            return
        conn.profile = clean_profile(msg.get("user"))
        await manager.play_bot(ws)

    elif mtype == "volley":
        if conn.room is None or conn.slot is None:
            return
        cells = msg.get("cells") or []
        await conn.room.handle_volley(conn.slot, cells)

    elif mtype == "ready":
        if conn.room is None or conn.slot is None:
            return
        await conn.room.handle_ready(conn.slot)

    elif mtype == "rematch":
        if conn.room is None or conn.slot is None:
            return
        await conn.room.handle_rematch(conn.slot)

    elif mtype == "leave":
        await manager.disconnect(ws)


# Статику монтируем последней, чтобы /ws и /api/* имели приоритет.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
