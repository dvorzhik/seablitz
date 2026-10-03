"""SeaBlitz — FastAPI-приложение: WebSocket-комнаты и раздача Mini App."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.net.rooms import Conn, RoomManager

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="SeaBlitz")
manager = RoomManager()


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "rooms": len(manager.rooms)}


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
        code = str(msg.get("code") or "").strip().upper()[:8] or "LOBBY"
        await manager.join_by_code(ws, code)

    elif mtype == "quickmatch":
        if conn.room is not None:
            return
        await manager.enqueue(ws)

    elif mtype == "cancel":
        await manager.cancel_search(ws)

    elif mtype == "leave_room":
        await manager.leave_room(ws)

    elif mtype == "play_bot":
        if conn.room is not None:
            return
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
