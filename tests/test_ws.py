"""End-to-end тест WebSocket-дуэли через TestClient (без реального сервера)."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from app.main import app

CELLS = [(r, c) for r in range(5) for c in range(5)]


def rand_cells(n: int = 3):
    cells = list(CELLS)
    random.shuffle(cells)
    return [list(c) for c in cells[:n]]


@pytest.fixture
def fast_timers(monkeypatch):
    """Ускоряем таймеры, чтобы тест не ждал 6 секунд на раунд."""
    monkeypatch.setattr("app.net.rooms.ROUND_SECONDS", 0.5)
    monkeypatch.setattr("app.net.rooms.TIEBREAK_SECONDS", 0.3)
    monkeypatch.setattr("app.net.rooms.RESULT_PAUSE_SECONDS", 0.01)
    monkeypatch.setattr("app.net.rooms.GATE_SECONDS", 0.05)


def test_full_match_over_websocket(fast_timers):
    client = TestClient(app)
    code = "TESTRM"

    with client.websocket_connect("/ws") as a:
        a.send_json({"type": "join", "code": code})
        assert a.receive_json()["type"] == "joined"

        with client.websocket_connect("/ws") as b:
            b.send_json({"type": "join", "code": code})
            assert b.receive_json()["type"] == "joined"

            over_a = None
            for _ in range(300):
                msg = a.receive_json()
                mtype = msg["type"]
                if mtype in ("round_start", "tiebreak_start"):
                    a.send_json({"type": "volley", "cells": rand_cells(3)})
                    b.send_json({"type": "volley", "cells": rand_cells(3)})
                elif mtype in ("battle_report", "overtime_intro"):
                    a.send_json({"type": "ready"})
                    b.send_json({"type": "ready"})
                elif mtype == "game_over":
                    over_a = msg
                    break

            assert over_a is not None, "первый игрок не дождался game_over"

            over_b = None
            for _ in range(300):
                msg = b.receive_json()
                if msg["type"] == "game_over":
                    over_b = msg
                    break

            assert over_b is not None, "второй игрок не дождался game_over"
            assert over_a["winner"] == over_b["winner"]
            assert over_a["winner"] in (0, 1)
            assert over_a["you_won"] != over_b["you_won"]


def test_quickmatch_pairs_two_players(fast_timers):
    client = TestClient(app)
    with client.websocket_connect("/ws") as a:
        a.send_json({"type": "quickmatch"})
        assert a.receive_json()["type"] == "waiting"

        with client.websocket_connect("/ws") as b:
            b.send_json({"type": "quickmatch"})
            joined = b.receive_json()
            assert joined["type"] == "joined"
            assert joined["code"]
            # после спаривания обоим приходит состояние поля
            assert a.receive_json()["type"] in ("joined", "state")
