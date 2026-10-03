"""Проверка продакшн-WebSocket: два клиента играют матч на удалённом сервере.

Запуск:
    python scripts/remote_check.py wss://seablitz.duckdns.org/ws
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


async def player(code: str, results: dict, idx: int) -> None:
    async with websockets.connect(URL, open_timeout=20) as ws:
        await ws.send(json.dumps({"type": "join", "code": code}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
            mtype = msg.get("type")
            if mtype in ("round_start", "tiebreak_start"):
                await ws.send(json.dumps({"type": "volley", "cells": rand_cells(3)}))
            elif mtype in ("battle_report", "overtime_intro"):
                await ws.send(json.dumps({"type": "ready"}))
            elif mtype == "game_over":
                results[idx] = msg
                return
            elif mtype == "opponent_left":
                results[idx] = msg
                return


async def main() -> None:
    code = "R" + str(random.randint(100, 999))
    results: dict = {}
    await asyncio.gather(player(code, results, 0), player(code, results, 1))
    assert results.get(0, {}).get("type") == "game_over", results
    assert results.get(1, {}).get("type") == "game_over", results
    assert results[0]["winner"] == results[1]["winner"]
    assert results[0].get("final") is True
    print(f"REMOTE WS OK ({URL}): winner={results[0]['winner']}, "
          f"you_won={results[0]['you_won']}/{results[1]['you_won']}")


if __name__ == "__main__":
    asyncio.run(main())
