"""WebSocket-комнаты «Морского блица»: дуэль двух игроков в реальном времени."""
from __future__ import annotations

import asyncio
import random
import string
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional

from fastapi import WebSocket

from app.config import settings
from app.game.board import ShotOutcome
from app.game.match import (
    Match,
    MatchConfig,
    PlayerRoundReport,
    RoundResult,
    TiebreakResult,
)

ROUND_SECONDS = 10.0
TIEBREAK_SECONDS = 10.0
RESULT_PAUSE_SECONDS = 1.5
GATE_SECONDS = 10.0
OVERTIME_INTRO_SECONDS = 15.0
REMATCH_WINDOW_SECONDS = 120.0
SEARCH_TIMEOUT_SECONDS = 20.0
BOT_MIN_DELAY = 1.5
BOT_MAX_DELAY = 4.0
# Бот «нажимает Готов» в гейтах овертайма (картина боя и правила) чуть быстрее,
# чем стреляет, — чтобы бой не зависел от повторных кликов живого игрока.
BOT_READY_MIN_DELAY = 0.4
BOT_READY_MAX_DELAY = 1.2


def make_code(length: int = 4) -> str:
    return "".join(random.choice(string.ascii_uppercase) for _ in range(length))


def share_url() -> str:
    """Публичная ссылка на бота/Mini App (для приглашений)."""
    return f"https://t.me/{settings.bot_username or 'seablitz_bot'}"


# Профиль бота-соперника: у бота нет initData — показываем @Cap'nBot и флаг.
BOT_PROFILE = {"username": "Cap'nBot", "name": None, "photo_url": None, "is_bot": True}


def clean_profile(raw: object) -> dict:
    """Нормализует профиль игрока из initData (username / имя / аватар)."""
    if not isinstance(raw, dict):
        return {}
    profile: dict = {}
    username = raw.get("username")
    if isinstance(username, str) and username.strip():
        profile["username"] = username.strip()[:32]
    name = raw.get("name")
    if isinstance(name, str) and name.strip():
        profile["name"] = name.strip()[:48]
    photo = raw.get("photo_url")
    if isinstance(photo, str) and photo.startswith("http"):
        profile["photo_url"] = photo[:600]
    return profile


async def safe_send(ws: WebSocket, payload: dict) -> None:
    """Отправка, которая не роняет комнату из-за закрытого сокета."""
    try:
        await ws.send_json(payload)
    except Exception:
        pass


@dataclass
class Conn:
    """Состояние одного WebSocket-подключения."""

    ws: WebSocket
    room: Optional["Room"] = None
    slot: Optional[int] = None
    profile: Optional[dict] = None


class Room:
    """Одна дуэль: два игрока, поле, таймеры раундов и «Золотой раунд»."""

    def __init__(
        self,
        code: str,
        manager: "RoomManager",
        config: MatchConfig | None = None,
    ) -> None:
        self.code = code
        self.manager = manager
        self.config = config or MatchConfig()
        self.sockets: Dict[int, WebSocket] = {}
        self.match: Optional[Match] = None
        self.volleys: Dict[int, List[List[int]]] = {}
        self.phase = "lobby"
        self.rng = random.Random()
        self._timer: Optional[asyncio.Task] = None
        self._gen = 0
        self._ready: set = set()
        self._gate_goto: Optional[str] = None
        self.rematch_requests: set = set()
        self.bot_slot: Optional[int] = None
        self.profiles: Dict[int, dict] = {}
        self._bot_task: Optional[asyncio.Task] = None
        self._bot_ready_task: Optional[asyncio.Task] = None

    def _occupied_slots(self) -> set:
        """Занятые слоты, включая бота (у бота нет сокета)."""
        slots = set(self.sockets)
        if self.bot_slot is not None:
            slots.add(self.bot_slot)
        return slots

    @property
    def full(self) -> bool:
        return len(self._occupied_slots()) >= self.config.players

    def add_player(self, ws: WebSocket, profile: Optional[dict] = None) -> int:
        occupied = self._occupied_slots()
        slot = 0 if 0 not in occupied else 1
        self.sockets[slot] = ws
        if profile:
            self.profiles[slot] = dict(profile)
        return slot

    def add_bot(self) -> int:
        occupied = self._occupied_slots()
        slot = 0 if 0 not in occupied else 1
        self.bot_slot = slot
        self.profiles[slot] = dict(BOT_PROFILE)
        return slot

    def _players_payload(self) -> List[dict]:
        """Публичные профили слотов — чтобы показать «кто с кем играет»."""
        players: List[dict] = []
        for slot in sorted(self._occupied_slots()):
            profile = self.profiles.get(slot, {})
            players.append(
                {
                    "slot": slot,
                    "username": profile.get("username"),
                    "name": profile.get("name"),
                    "photo_url": profile.get("photo_url"),
                    "is_bot": slot == self.bot_slot,
                }
            )
        return players

    def _new_match(self) -> None:
        """(Пере)создаёт матч — используется при старте и реванше."""
        self.match = Match(config=self.config, rng=self.rng)
        self.volleys = {}
        self._ready = set()
        self._gate_goto = None
        self.rematch_requests = set()
        self.phase = "playing"

    async def start(self) -> None:
        self._new_match()
        for slot, ws in self.sockets.items():
            await safe_send(
                ws,
                {
                    "type": "state",
                    "code": self.code,
                    "slot": slot,
                    "players": self._players_payload(),
                    "view": self.match.view_for(slot),
                },
            )
        await self._start_round()

    @staticmethod
    def _cancel_task(task: Optional[asyncio.Task]) -> None:
        """Отменяет задачу, но никогда не пытается отменить саму себя.

        Гейты овертайма открываются из задачи бота (``_bot_ready``), а
        ``_finish_round`` может быть вызван из задачи залпа бота. Отмена
        текущей задачи привела бы к тому, что ``await`` внутри обработчика
        получил бы ``CancelledError`` и прервал работу — например, бот не
        успевал запланировать залп в «Золотом раунде».
        """
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()

    def _cancel_timer(self) -> None:
        timer = self._timer
        self._timer = None
        self._cancel_task(timer)

    def _schedule(self, seconds: float, kind: str) -> None:
        """Ставит таймер раунда; по истечении — добивание случайными выстрелами."""
        self._cancel_timer()
        self._gen += 1
        gen = self._gen

        async def runner() -> None:
            try:
                await asyncio.sleep(seconds)
            except asyncio.CancelledError:
                return
            if gen != self._gen:
                return
            await self._finish_round(kind)

        self._timer = asyncio.create_task(runner())

    def _after_pause(self, factory: Callable[[], Awaitable[None]]) -> None:
        """Небольшая пауза (для анимаций), затем запуск следующей фазы."""
        self._cancel_timer()
        self._gen += 1
        gen = self._gen

        async def runner() -> None:
            try:
                await asyncio.sleep(RESULT_PAUSE_SECONDS)
            except asyncio.CancelledError:
                return
            if gen != self._gen:
                return
            await factory()

        self._timer = asyncio.create_task(runner())

    async def _start_round(self) -> None:
        self.phase = "playing"
        self.volleys = {}
        await self._broadcast(
            {
                "type": "round_start",
                "code": self.code,
                "round": self.match.round_no + 1,
                "phase": "playing",
                "timeout_ms": int(ROUND_SECONDS * 1000),
                "shots": self.config.shots_per_round,
            }
        )
        self._schedule(ROUND_SECONDS, "playing")
        self._schedule_bot()

    async def _start_tiebreak(self) -> None:
        self.phase = "tiebreak"
        self.volleys = {}
        board = self.match.tiebreak_board
        await self._broadcast(
            {
                "type": "tiebreak_start",
                "code": self.code,
                "round": self.match.tiebreak_round + 1,
                "phase": "tiebreak",
                "timeout_ms": int(TIEBREAK_SECONDS * 1000),
                "shots": self.config.tiebreak_shots,
                "ships_total": sum(len(ship) for ship in board.ships),
            }
        )
        self._schedule(TIEBREAK_SECONDS, "tiebreak")
        self._schedule_bot()

    async def _broadcast(self, payload: dict) -> None:
        for ws in list(self.sockets.values()):
            await safe_send(ws, payload)

    # --- бот-соперник ---
    def _cancel_bot(self) -> None:
        task = self._bot_task
        self._bot_task = None
        self._cancel_task(task)
        self._cancel_bot_ready()

    def _cancel_bot_ready(self) -> None:
        task = self._bot_ready_task
        self._bot_ready_task = None
        self._cancel_task(task)

    def _schedule_bot_ready(self) -> None:
        """Бот «нажимает Готов» в гейте овертайма (у бота нет сокета)."""
        self._cancel_bot_ready()
        if self.bot_slot is None or self._gate_goto is None:
            return
        delay = self.rng.uniform(BOT_READY_MIN_DELAY, BOT_READY_MAX_DELAY)
        self._bot_ready_task = asyncio.create_task(self._bot_ready(delay))

    async def _bot_ready(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if self.bot_slot is None or self._gate_goto is None:
            return
        await self._mark_ready(self.bot_slot)

    def _schedule_bot(self) -> None:
        if self.bot_slot is None or self.match is None:
            return
        self._cancel_bot()
        delay = self.rng.uniform(BOT_MIN_DELAY, BOT_MAX_DELAY)
        self._bot_task = asyncio.create_task(self._bot_act(delay))

    async def _bot_act(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if self.bot_slot is None or self.match is None:
            return
        if self.phase not in ("playing", "tiebreak") or self.bot_slot in self.volleys:
            return
        if self.phase == "playing":
            target = self.match.opponent_board(self.bot_slot)
            cells = self._bot_cells(target, self.config.shots_per_round)
        else:
            cells = self._bot_cells(
                self.match.tiebreak_board, self.config.tiebreak_shots
            )
        await self.handle_volley(self.bot_slot, cells)

    def _bot_cells(self, board, shots: int) -> List[List[int]]:
        """Стратегия бота: добивать соседей попаданий, иначе — случайно."""
        unfired = set(board.unfired_cells())
        hits = [
            cell
            for cell, res in board.shots.items()
            if res.outcome is not ShotOutcome.MISS
        ]
        cand: List = []
        for h in hits:
            for nb in ((h[0] + 1, h[1]), (h[0] - 1, h[1]), (h[0], h[1] + 1), (h[0], h[1] - 1)):
                if nb in unfired:
                    cand.append(nb)
        self.rng.shuffle(cand)
        picks: List = []
        seen: set = set()
        for cell in cand:
            if cell not in seen:
                seen.add(cell)
                picks.append(cell)
            if len(picks) == shots:
                break
        pool = [c for c in unfired if c not in seen]
        self.rng.shuffle(pool)
        while len(picks) < shots and pool:
            picks.append(pool.pop())
        return [[r, c] for (r, c) in picks]

    async def handle_volley(self, slot: int, cells: list) -> None:
        """Принимает залп игрока; при готовности обоих — разрешает раунд."""
        if self.match is None or self.phase not in ("playing", "tiebreak"):
            return
        if slot in self.volleys:
            return  # игрок уже отстрелялся в этом раунде
        clean: List[List[int]] = []
        for cell in cells or []:
            try:
                r, c = int(cell[0]), int(cell[1])
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            clean.append([r, c])
        self.volleys[slot] = clean
        if len(self.volleys) >= self.config.players:
            # Оба нажали «ОГОНЬ!» — разрешаем раунд сразу, не ждём таймера.
            await self._finish_round(self.phase)
        else:
            for other, ws in list(self.sockets.items()):
                if other != slot:
                    await safe_send(ws, {"type": "opponent_locked", "code": self.code})

    def _shots_payload(self, report: PlayerRoundReport) -> List[dict]:
        out: List[dict] = []
        for s in report.shots:
            item = {"cell": list(s.cell), "outcome": s.outcome.value}
            if s.sunk_ship is not None:
                item["ship"] = [list(c) for c in s.sunk_ship]
            out.append(item)
        return out

    def _round_payload(self, slot: int, result: RoundResult) -> dict:
        return {
            "type": "round_result",
            "code": self.code,
            "round": result.round_no,
            "phase": self.match.phase,
            "finished": result.finished,
            "winner": result.winner,
            "needs_tiebreak": result.needs_tiebreak,
            "your_shots": self._shots_payload(result.players[slot]),
            "enemy_shots": self._shots_payload(result.players[1 - slot]),
            "your_hits": result.players[slot].hits,
            "view": self.match.view_for(slot),
        }

    def _tiebreak_payload(self, slot: int, result: TiebreakResult, board) -> dict:
        def mark(cells) -> List[dict]:
            return [
                {"cell": [r, c], "hit": board.is_ship_cell((r, c))}
                for (r, c) in cells
            ]

        ships = [list(cell) for ship in board.ships for cell in ship]
        return {
            "type": "tiebreak_result",
            "code": self.code,
            "round": result.round_no,
            "finished": result.finished,
            "winner": result.winner,
            "need_repeat": result.need_repeat,
            "your_hits": result.hits[slot],
            "enemy_hits": result.hits[1 - slot],
            "your_shots": mark(result.shots[slot]),
            "enemy_shots": mark(result.shots[1 - slot]),
            "ships": ships,
        }

    async def _finish_round(self, kind: str) -> None:
        self._cancel_timer()
        self._cancel_bot()
        if kind == "playing":
            result = self.match.resolve_round(self.volleys)
            self.volleys = {}
            for slot, ws in list(self.sockets.items()):
                await safe_send(ws, self._round_payload(slot, result))
            if result.finished:
                await self._finish_game()
            elif result.needs_tiebreak:
                await self._send_battle_report()
            else:
                self._after_pause(self._start_round)
        else:
            board = self.match.tiebreak_board
            result = self.match.resolve_tiebreak(self.volleys)
            self.volleys = {}
            for slot, ws in list(self.sockets.items()):
                await safe_send(ws, self._tiebreak_payload(slot, result, board))
            if result.finished:
                await self._finish_game(tiebreak=(board, result))
            else:
                self._after_pause(self._start_tiebreak)

    def _battle_view(self, slot: int) -> dict:
        """Полная «картина сражения»: оба флота раскрыты + статистика."""
        view = self.match.view_for(slot)
        view["enemy_ships"] = [
            list(ship) for ship in self.match.boards[1 - slot].ships
        ]
        your_shots = view["your_shots"]
        enemy_shots = view["enemy_shots"]
        view["stats"] = {
            "rounds": self.match.round_no,
            "tiebreak_rounds": self.match.tiebreak_round,
            "your_hits": sum(1 for s in your_shots if s["outcome"] != "miss"),
            "enemy_hits": sum(1 for s in enemy_shots if s["outcome"] != "miss"),
            "your_shots": len(your_shots),
            "enemy_shots": len(enemy_shots),
        }
        return view

    async def _send_battle_report(self) -> None:
        """Картина боя; после «готов» — правила овертайма."""
        self.phase = "report"
        for slot, ws in list(self.sockets.items()):
            await safe_send(
                ws,
                {
                    "type": "battle_report",
                    "code": self.code,
                    "final": False,
                    "draw": True,
                    "gate_ms": int(GATE_SECONDS * 1000),
                    "view": self._battle_view(slot),
                },
            )
        self._start_gate("overtime")

    async def _send_overtime_intro(self) -> None:
        self.phase = "overtime_intro"
        for slot, ws in list(self.sockets.items()):
            await safe_send(
                ws,
                {
                    "type": "overtime_intro",
                    "code": self.code,
                    "gate_ms": int(OVERTIME_INTRO_SECONDS * 1000),
                    "timeout_ms": int(TIEBREAK_SECONDS * 1000),
                    "shots": self.config.tiebreak_shots,
                },
            )
        self._start_gate("tiebreak", OVERTIME_INTRO_SECONDS)

    def _start_gate(self, goto: str, seconds: float | None = None) -> None:
        """Ждём «готов» от обоих игроков либо истечение таймера."""
        if seconds is None:
            seconds = GATE_SECONDS
        self._ready = set()
        self._gate_goto = goto
        self._cancel_timer()
        self._gen += 1
        gen = self._gen

        async def runner() -> None:
            try:
                await asyncio.sleep(seconds)
            except asyncio.CancelledError:
                return
            if gen != self._gen:
                return
            await self._open_gate()

        self._timer = asyncio.create_task(runner())
        self._schedule_bot_ready()

    async def _open_gate(self) -> None:
        goto = self._gate_goto
        self._gate_goto = None
        self._cancel_timer()
        self._cancel_bot_ready()
        if goto == "overtime":
            await self._send_overtime_intro()
        elif goto == "tiebreak":
            await self._start_tiebreak()

    async def handle_ready(self, slot: int) -> None:
        """Игрок нажал «Продолжить»/«Начать»."""
        await self._mark_ready(slot)

    async def _mark_ready(self, slot: int) -> None:
        """Отмечает готовность слота (игрока или бота) и открывает гейт."""
        if self._gate_goto is None:
            return
        self._ready.add(slot)
        if len(self._ready) >= len(self._occupied_slots()):
            await self._open_gate()

    async def handle_rematch(self, slot: int) -> None:
        """Игрок предложил/принял реванш; когда готовы оба — новый матч."""
        if self.phase != "finished" or self.match is None:
            return
        self.rematch_requests.add(slot)
        if len(self.rematch_requests) >= len(self.sockets):
            await self._start_rematch()
            return
        for other, ws in list(self.sockets.items()):
            if other != slot:
                await safe_send(ws, {"type": "rematch_request", "code": self.code})

    async def _start_rematch(self) -> None:
        self._cancel_timer()
        self._new_match()
        for slot, ws in list(self.sockets.items()):
            await safe_send(ws, {"type": "rematch_start", "code": self.code})
            await safe_send(
                ws,
                {
                    "type": "state",
                    "code": self.code,
                    "slot": slot,
                    "players": self._players_payload(),
                    "view": self.match.view_for(slot),
                },
            )
        await self._start_round()

    def _schedule_cleanup(self) -> None:
        """Закрывает комнату, если реванш не начался за отведённое окно."""
        self._cancel_timer()
        self._gen += 1
        gen = self._gen

        async def runner() -> None:
            try:
                await asyncio.sleep(REMATCH_WINDOW_SECONDS)
            except asyncio.CancelledError:
                return
            if gen != self._gen:
                return
            self.manager.drop(self.code)

        self._timer = asyncio.create_task(runner())

    def _tiebreak_picture(self, slot: int, board, result: TiebreakResult) -> dict:
        """Картина «Золотого раунда»: общее поле + выстрелы обоих игроков."""
        def mark(cells) -> List[dict]:
            return [
                {"cell": [r, c], "hit": board.is_ship_cell((r, c))}
                for (r, c) in cells
            ]

        return {
            "round": result.round_no,
            "ships": [list(cell) for ship in board.ships for cell in ship],
            "your_shots": mark(result.shots[slot]),
            "enemy_shots": mark(result.shots[1 - slot]),
            "your_hits": result.hits[slot],
            "enemy_hits": result.hits[1 - slot],
        }

    async def _finish_game(self, tiebreak=None) -> None:
        self._cancel_timer()
        self.phase = "finished"
        share = share_url()
        for slot, ws in list(self.sockets.items()):
            payload = {
                "type": "game_over",
                "code": self.code,
                "final": True,
                "winner": self.match.winner,
                "you_won": self.match.winner == slot,
                "share_url": share,
            }
            if tiebreak is not None:
                board, result = tiebreak
                payload["mode"] = "tiebreak"
                payload["picture"] = self._tiebreak_picture(slot, board, result)
            else:
                payload["mode"] = "main"
                payload["view"] = self._battle_view(slot)
            await safe_send(ws, payload)
        self._schedule_cleanup()

    async def remove_player(self, slot: int) -> None:
        self.sockets.pop(slot, None)
        self._cancel_timer()
        self._cancel_bot()
        for ws in list(self.sockets.values()):
            await safe_send(ws, {"type": "opponent_left", "code": self.code})
        self.manager.drop(self.code)


class RoomManager:
    """Хранилище комнат, быстрый матч и учёт подключений (в оперативной памяти)."""

    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}
        self.conns: Dict[WebSocket, Conn] = {}
        self.queue: List[WebSocket] = []
        self._search_timers: Dict[WebSocket, asyncio.Task] = {}

    def _cancel_search_timer(self, ws: WebSocket) -> None:
        task = self._search_timers.pop(ws, None)
        if task is not None and not task.done():
            task.cancel()

    def _start_search_timer(self, ws: WebSocket) -> None:
        """Через SEARCH_TIMEOUT_SECONDS сообщаем, что соперник не нашёлся."""
        self._cancel_search_timer(ws)

        async def runner() -> None:
            try:
                await asyncio.sleep(SEARCH_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                return
            if ws in self.queue:
                await safe_send(
                    ws, {"type": "search_timeout", "share_url": share_url()}
                )

        self._search_timers[ws] = asyncio.create_task(runner())

    async def _place(self, room: Room, ws: WebSocket) -> int:
        conn = self.conns.get(ws)
        profile = conn.profile if conn is not None else None
        slot = room.add_player(ws, profile)
        if conn is not None:
            conn.room = room
            conn.slot = slot
        await safe_send(ws, {"type": "joined", "code": room.code, "slot": slot})
        return slot

    async def join_by_code(self, ws: WebSocket, code: str) -> None:
        # выход из очереди быстрого поиска, если игрок там был
        if ws in self.queue:
            self.queue.remove(ws)
        self._cancel_search_timer(ws)
        room = self.rooms.get(code)
        if room is None:
            room = Room(code, self)
            self.rooms[code] = room
        if room.full or room.phase != "lobby":
            await safe_send(ws, {"type": "error", "message": "room_unavailable"})
            return
        await self._place(room, ws)
        if room.full:
            await room.start()
        else:
            await safe_send(
                ws,
                {"type": "waiting", "code": room.code, "share_url": share_url()},
            )

    async def enqueue(self, ws: WebSocket) -> Optional[Room]:
        if ws not in self.queue:
            self.queue.append(ws)
        if len(self.queue) < 2:
            await safe_send(
                ws, {"type": "waiting", "code": None, "share_url": share_url()}
            )
            self._start_search_timer(ws)
            return None
        a = self.queue.pop(0)
        b = self.queue.pop(0)
        self._cancel_search_timer(a)
        self._cancel_search_timer(b)
        code = make_code()
        while code in self.rooms:
            code = make_code()
        room = Room(code, self)
        self.rooms[code] = room
        await self._place(room, a)
        await self._place(room, b)
        await room.start()
        return room

    async def cancel_search(self, ws: WebSocket) -> None:
        if ws in self.queue:
            self.queue.remove(ws)
        self._cancel_search_timer(ws)
        await safe_send(ws, {"type": "search_cancelled", "share_url": share_url()})

    async def leave_room(self, ws: WebSocket) -> None:
        """Выйти из созданной комнаты, не разрывая соединение."""
        conn = self.conns.get(ws)
        if conn is None or conn.room is None:
            return
        room = conn.room
        slot = conn.slot
        conn.room = None
        conn.slot = None
        if slot is not None:
            await room.remove_player(slot)
        await safe_send(ws, {"type": "left_room"})

    async def play_bot(self, ws: WebSocket) -> Room:
        """Игра против бота — для тренировки при пустом онлайне."""
        if ws in self.queue:
            self.queue.remove(ws)
        self._cancel_search_timer(ws)
        code = make_code()
        while code in self.rooms:
            code = make_code()
        room = Room(code, self)
        self.rooms[code] = room
        await self._place(room, ws)
        room.add_bot()
        await room.start()
        return room

    async def disconnect(self, ws: WebSocket) -> None:
        conn = self.conns.pop(ws, None)
        self._cancel_search_timer(ws)
        if ws in self.queue:
            self.queue.remove(ws)
        if conn is not None and conn.room is not None and conn.slot is not None:
            await conn.room.remove_player(conn.slot)

    def drop(self, code: str) -> None:
        self.rooms.pop(code, None)
