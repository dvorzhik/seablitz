"""Headless end-to-end прогон: два клиента играют полный матч через WebSocket.

Запуск:  python scripts/ws_smoke.py
Поднимает локальный uvicorn, подключает двух игроков в одну комнату, случайно
стреляет, ждёт game_over и проверяет, что победитель определён корректно.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
import sys
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
PORT = 8137
HTTP = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}/ws"


def rand_cells(n: int = 3):
    cells = [(r, c) for r in range(5) for c in range(5)]
    random.shuffle(cells)
    return [list(c) for c in cells[:n]]


async def player(code: str, results: dict, idx: int) -> None:
    async with websockets.connect(WS, open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "join", "code": code}))
        games = 0
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            msg = json.loads(raw)
            mtype = msg.get("type")
            if mtype == "round_start":
                await ws.send(json.dumps({"type": "volley", "cells": rand_cells(3)}))
            elif mtype == "tiebreak_start":
                await ws.send(json.dumps({"type": "volley", "cells": rand_cells(3)}))
            elif mtype in ("battle_report", "overtime_intro"):
                await ws.send(json.dumps({"type": "ready"}))
            elif mtype == "game_over":
                games += 1
                if games == 1:
                    # предложить реванш и сыграть второй матч
                    await ws.send(json.dumps({"type": "rematch"}))
                else:
                    results[idx] = msg
                    return
            elif mtype == "opponent_left":
                results[idx] = msg
                return


async def main() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--port", str(PORT), "--log-level", "warning",
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(HTTP + "/api/health", timeout=1)
                break
            except Exception:
                await asyncio.sleep(0.2)
        else:
            raise SystemExit("server did not start")

        results: dict = {}
        await asyncio.gather(player("SMOKE", results, 0), player("SMOKE", results, 1))

        assert results.get(0, {}).get("type") == "game_over", results
        assert results.get(1, {}).get("type") == "game_over", results
        assert results[0].get("final") is True, results
        assert "enemy_ships" in results[0].get("view", {}), results
        w0, w1 = results[0]["winner"], results[1]["winner"]
        assert w0 == w1 and w0 in (0, 1), results
        assert results[0]["you_won"] != results[1]["you_won"], results
        print(f"SMOKE OK: 2 матча подряд (с реваншем), победитель второго = player {w0}")
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
