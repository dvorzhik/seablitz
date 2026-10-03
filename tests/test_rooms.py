"""Тесты логики комнаты: «картина боя», «готов»-гейт и флоу овертайма."""
from __future__ import annotations

import asyncio
import random

from app.game.match import Match, MatchConfig
from app.net.rooms import Conn, Room, RoomManager


class FakeWS:
    def __init__(self) -> None:
        self.sent: list = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class StubManager:
    def __init__(self) -> None:
        self.dropped: list = []

    def drop(self, code: str) -> None:
        self.dropped.append(code)


def _room_with_match():
    """Комната с матчем, доведённым до обоюдного KO (готовым к овертайму)."""
    cfg = MatchConfig(fleet=(1,), shots_per_round=1, tiebreak_shots=1)
    manager = StubManager()
    room = Room("TEST", manager, cfg)
    room.match = Match(
        config=cfg,
        rng=random.Random(0),
        fleets={0: [((0, 0),)], 1: [((0, 0),)]},
    )
    room.match.resolve_round({0: [(0, 0)], 1: [(0, 0)]})  # обоюдный KO
    a, b = FakeWS(), FakeWS()
    room.add_player(a)
    room.add_player(b)
    return room, a, b, manager


def test_gate_flow_battle_report_overtime_tiebreak():
    async def scenario():
        room, a, _b, _m = _room_with_match()
        await room._send_battle_report()

        assert a.sent[-1]["type"] == "battle_report"
        assert a.sent[-1]["final"] is False
        assert a.sent[-1]["draw"] is True
        assert a.sent[-1]["view"]["enemy_ships"]  # флот врага раскрыт
        assert "stats" in a.sent[-1]["view"]

        await room.handle_ready(0)
        assert a.sent[-1]["type"] == "battle_report"  # ждём второго игрока

        await room.handle_ready(1)
        assert a.sent[-1]["type"] == "overtime_intro"

        await room.handle_ready(0)
        await room.handle_ready(1)
        assert a.sent[-1]["type"] == "tiebreak_start"
        assert room.phase == "tiebreak"
        room._cancel_timer()

    asyncio.run(scenario())


def test_game_over_report_includes_enemy_ships():
    async def scenario():
        room, a, b, manager = _room_with_match()
        room.match.winner = 0
        await room._finish_game()

        assert a.sent[-1]["type"] == "game_over"
        assert a.sent[-1]["final"] is True
        assert a.sent[-1]["you_won"] is True
        assert b.sent[-1]["you_won"] is False
        assert a.sent[-1]["view"]["enemy_ships"]
        assert room.phase == "finished"
        assert manager.dropped == []  # комната живёт — можно предложить реванш
        room._cancel_timer()

    asyncio.run(scenario())


def test_rematch_flow():
    async def scenario():
        room, a, _b, _m = _room_with_match()
        room.match.winner = 0
        await room._finish_game()

        # проигравший (slot 1) предлагает реванш — победителю приходит вызов
        await room.handle_rematch(1)
        assert a.sent[-1]["type"] == "rematch_request"
        assert room.phase == "finished"

        # победитель (slot 0) принимает — стартует новый матч
        await room.handle_rematch(0)
        assert any(m["type"] == "rematch_start" for m in a.sent)
        assert a.sent[-1]["type"] == "round_start"
        assert room.phase == "playing"
        room._cancel_timer()

    asyncio.run(scenario())


def test_gate_times_out_without_ready(monkeypatch):
    monkeypatch.setattr("app.net.rooms.GATE_SECONDS", 0.05)

    async def scenario():
        room, a, _b, _m = _room_with_match()
        await room._send_battle_report()
        await asyncio.sleep(0.25)  # гейт должен сам перейти к овертайму
        assert any(m["type"] == "overtime_intro" for m in a.sent)
        room._cancel_timer()

    asyncio.run(scenario())


def test_join_by_code_sends_waiting_with_share_url():
    async def scenario():
        manager = RoomManager()
        ws = FakeWS()
        manager.conns[ws] = Conn(ws=ws)
        await manager.join_by_code(ws, "ABCD")
        assert ws.sent[-1]["type"] == "waiting"
        assert ws.sent[-1]["code"] == "ABCD"
        assert ws.sent[-1]["share_url"].startswith("https://t.me/")
        manager.drop("ABCD")

    asyncio.run(scenario())


def test_volley_notifies_opponent():
    async def scenario():
        room, _a, b, _m = _room_with_match()
        room.phase = "playing"
        room.volleys = {}
        await room.handle_volley(0, [(0, 0)])
        # раунд ещё не разрешён, но соперник получает сигнал «выстрелил»
        assert any(m["type"] == "opponent_locked" for m in b.sent)

    asyncio.run(scenario())


def test_game_over_after_tiebreak_shows_picture():
    async def scenario():
        room, a, _b, _m = _room_with_match()  # уже обоюдный KO
        room.phase = "tiebreak"
        board = room.match.tiebreak_board
        ship = next(c for c in board.all_cells() if board.is_ship_cell(c))
        water = next(c for c in board.all_cells() if not board.is_ship_cell(c))

        await room.handle_volley(0, [list(ship)])
        await room.handle_volley(1, [list(water)])

        over = a.sent[-1]
        assert over["type"] == "game_over"
        assert over["mode"] == "tiebreak"
        assert over["final"] is True
        assert over["you_won"] is True
        assert over["picture"]["ships"]
        assert over["picture"]["your_hits"] == 1
        assert over["picture"]["enemy_hits"] == 0
        assert over["share_url"].startswith("https://t.me/")
        room._cancel_timer()

    asyncio.run(scenario())


def test_cancel_search_removes_from_queue():
    async def scenario():
        manager = RoomManager()
        ws = FakeWS()
        manager.conns[ws] = Conn(ws=ws)
        await manager.enqueue(ws)
        assert ws in manager.queue
        await manager.cancel_search(ws)
        assert ws not in manager.queue
        assert ws.sent[-1]["type"] == "search_cancelled"

    asyncio.run(scenario())


def test_search_timeout_notifies(monkeypatch):
    monkeypatch.setattr("app.net.rooms.SEARCH_TIMEOUT_SECONDS", 0.05)

    async def scenario():
        manager = RoomManager()
        ws = FakeWS()
        manager.conns[ws] = Conn(ws=ws)
        await manager.enqueue(ws)
        await asyncio.sleep(0.2)
        assert any(m["type"] == "search_timeout" for m in ws.sent)
        manager._cancel_search_timer(ws)

    asyncio.run(scenario())


def test_play_bot_starts_match():
    async def scenario():
        manager = RoomManager()
        ws = FakeWS()
        manager.conns[ws] = Conn(ws=ws)
        room = await manager.play_bot(ws)

        assert room.bot_slot is not None
        assert room.phase == "playing"
        types = [m["type"] for m in ws.sent]
        assert "state" in types and "round_start" in types

        room._cancel_bot()
        await room.handle_volley(0, [[0, 0]])
        await room.handle_volley(room.bot_slot, [[1, 1]])
        assert any(m["type"] == "round_result" for m in ws.sent)
        room._cancel_timer()

    asyncio.run(scenario())


def test_bot_volleys_automatically(monkeypatch):
    monkeypatch.setattr("app.net.rooms.BOT_MIN_DELAY", 0.01)
    monkeypatch.setattr("app.net.rooms.BOT_MAX_DELAY", 0.02)

    async def scenario():
        manager = RoomManager()
        ws = FakeWS()
        manager.conns[ws] = Conn(ws=ws)
        room = await manager.play_bot(ws)
        await room.handle_volley(0, [[0, 0]])
        await asyncio.sleep(0.2)
        assert any(m["type"] == "round_result" for m in ws.sent)
        room._cancel_timer()
        room._cancel_bot()

    asyncio.run(scenario())
