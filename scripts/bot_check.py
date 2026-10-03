"""Проверка игры против бота на удалённом сервере.

Запуск: python scripts/bot_check.py [wss://seablitz.duckdns.org/ws]
"""
from __future__ import annotations

import asyncio
import json
import random
import sys

import websockets

URL = sys.argv[1] if len(sys.argv) > 1 else "wss://seablitz.duckdns.org/ws"


def rand_cells(n: int = 3):
    cells = [(r, c) for r in range(5) for c in range(5)]
    random.shuffle(cells)
    return [list(c) for c in cells[:n]]


async def main() -> None:
    start_only = "--start-only" in sys.argv
    async with websockets.connect(URL, open_timeout=20) as ws:
        await ws.send(json.dumps({"type": "play_bot"}))
        seen = []
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
            mtype = msg.get("type")
            seen.append(mtype)
            if mtype == "round_start":
                if start_only:
                    print("BOT START OK:", seen)
                    return
                await ws.send(json.dumps({"type": "volley", "cells": rand_cells(3)}))
            elif mtype == "tiebreak_start":
                await ws.send(json.dumps({"type": "volley", "cells": rand_cells(3)}))
            elif mtype in ("battle_report", "overtime_intro"):
                await ws.send(json.dumps({"type": "ready"}))
            elif mtype == "game_over":
                print(
                    f"BOT GAME OK: winner={msg['winner']} you_won={msg['you_won']} "
                    f"mode={msg.get('mode')}"
                )
                return
            elif mtype == "opponent_left":
                print("opponent_left")
                return


if __name__ == "__main__":
    asyncio.run(main())
