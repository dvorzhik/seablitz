"""Матч «Морского блица»: одновременные залпы и развязка раунда."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .board import Board, ShotOutcome, ShotResult
from .fleet import Cell, DEFAULT_COLS, DEFAULT_FLEET, DEFAULT_ROWS, generate_fleet

PlayerId = int


@dataclass
class MatchConfig:
    """Настройки партии (по умолчанию — дуэль 5x5, 3 выстрела в раунд)."""

    rows: int = DEFAULT_ROWS
    cols: int = DEFAULT_COLS
    fleet: Tuple[int, ...] = DEFAULT_FLEET
    shots_per_round: int = 3
    tiebreak_shots: int = 3
    players: int = 2


@dataclass
class PlayerRoundReport:
    """Итог раунда для одного игрока: его выстрелы по полю соперника."""

    shots: List[ShotResult] = field(default_factory=list)
    auto_filled: int = 0

    @property
    def hits(self) -> int:
        return sum(
            1 for s in self.shots if s.outcome in (ShotOutcome.HIT, ShotOutcome.SUNK)
        )

    @property
    def sunk(self) -> int:
        return sum(1 for s in self.shots if s.outcome is ShotOutcome.SUNK)


@dataclass
class RoundResult:
    """Результат раунда одновременного залпа."""

    round_no: int
    players: Dict[PlayerId, PlayerRoundReport]
    winner: Optional[PlayerId]
    draw: bool
    finished: bool
    needs_tiebreak: bool = False


@dataclass
class TiebreakResult:
    """Результат тайбрейк-раунда («Золотой раунд»).

    Оба игрока бьют по ОДНОМУ общему полю; побеждает тот, у кого больше
    попаданий. При полном равенстве попаданий поле пересоздаётся, и раунд
    повторяется (``need_repeat=True``).
    """

    round_no: int
    hits: Dict[PlayerId, int]
    shots: Dict[PlayerId, List[Cell]]
    auto_filled: Dict[PlayerId, int]
    winner: Optional[PlayerId]
    need_repeat: bool
    finished: bool


class Match:
    """Дуэль с одновременными залпами.

    Каждый раунд оба игрока выбирают до ``shots_per_round`` клеток на поле
    соперника. Недостающие выстрелы добиваются сервером случайно. Побеждает
    тот, кто потопил весь флот соперника.

    Если оба сделали это в одном раунде (обоюдный KO) — ничьей нет: матч
    уходит в «Золотой раунд» (:meth:`resolve_tiebreak`), где оба бьют по
    ОДНОМУ общему полю, а побеждает тот, у кого больше попаданий.
    """

    def __init__(
        self,
        config: MatchConfig | None = None,
        rng: random.Random | None = None,
        fleets: Optional[Dict[PlayerId, Sequence[Sequence[Cell]]]] = None,
    ) -> None:
        self.config = config or MatchConfig()
        self.rng = rng or random.Random()

        if fleets is not None:
            self.boards: Dict[PlayerId, Board] = {
                p: Board(fleets[p], self.config.rows, self.config.cols)
                for p in range(self.config.players)
            }
        else:
            self.boards = {
                p: Board(
                    generate_fleet(
                        self.config.rows,
                        self.config.cols,
                        self.config.fleet,
                        self.rng,
                    ),
                    self.config.rows,
                    self.config.cols,
                )
                for p in range(self.config.players)
            }

        self.round_no = 0
        self.finished = False
        self.draw = False
        self.winner: Optional[PlayerId] = None
        self.needs_tiebreak = False
        self.tiebreak_round = 0
        self.tiebreak_board: Optional[Board] = None

    def opponent_board(self, player: PlayerId) -> Board:
        """Поле соперника — цель выстрелов игрока ``player``."""
        return self.boards[1 - player]

    def _select_cells(
        self, board: Board, wanted: Sequence[Cell], limit: int
    ) -> Tuple[List[Cell], int]:
        """Отбирает валидные клетки и добивает недостающие случайными."""
        chosen: List[Cell] = []
        seen: set[Cell] = set()
        for cell in wanted:
            cell = (int(cell[0]), int(cell[1]))
            if not board.in_bounds(cell) or cell in seen or board.already_shot(cell):
                continue
            seen.add(cell)
            chosen.append(cell)
            if len(chosen) == limit:
                break

        auto_filled = 0
        need = limit - len(chosen)
        if need > 0:
            pool = [c for c in board.unfired_cells() if c not in seen]
            self.rng.shuffle(pool)
            for cell in pool[:need]:
                chosen.append(cell)
            auto_filled = min(need, len(pool))
        return chosen, auto_filled

    def _build_volley(
        self, player: PlayerId, wanted: Sequence[Cell]
    ) -> PlayerRoundReport:
        """Залп игрока по полю соперника с автодобиванием раунда."""
        target = self.opponent_board(player)
        chosen, auto_filled = self._select_cells(
            target, wanted, self.config.shots_per_round
        )
        report = PlayerRoundReport(auto_filled=auto_filled)
        for cell in chosen:
            report.shots.append(target.fire(cell))
        return report

    def resolve_round(
        self, volleys: Dict[PlayerId, Sequence[Cell]]
    ) -> RoundResult:
        """Разрешает раунд: применяет оба залпа и определяет исход.

        :raises RuntimeError: если партия уже завершена.
        """
        if self.finished:
            raise RuntimeError("match already finished")
        if self.needs_tiebreak:
            raise RuntimeError("match is in tiebreak phase")

        self.round_no += 1

        reports: Dict[PlayerId, PlayerRoundReport] = {
            p: self._build_volley(p, volleys.get(p, ()))
            for p in range(self.config.players)
        }

        # Игрок p победил, если полностью потопил флот соперника (boards[1-p]).
        destroyed_by = [
            p
            for p in range(self.config.players)
            if self.opponent_board(p).all_sunk()
        ]

        if len(destroyed_by) == self.config.players:
            # Обоюдный KO — уходим в «Золотой раунд» вместо ничьей.
            self.needs_tiebreak = True
            self.tiebreak_board = self._new_tiebreak_board()
            self.winner = None
            self.finished = False
        elif len(destroyed_by) == 1:
            self.winner = destroyed_by[0]
            self.finished = True

        return RoundResult(
            round_no=self.round_no,
            players=reports,
            winner=self.winner,
            draw=False,
            finished=self.finished,
            needs_tiebreak=self.needs_tiebreak,
        )

    def _new_tiebreak_board(self) -> Board:
        """Общее для обоих игроков поле «Золотого раунда»."""
        return Board(
            generate_fleet(
                self.config.rows,
                self.config.cols,
                self.config.fleet,
                self.rng,
            ),
            self.config.rows,
            self.config.cols,
        )

    @property
    def phase(self) -> str:
        """Текущая фаза матча: ``playing`` | ``tiebreak`` | ``finished``."""
        if self.finished:
            return "finished"
        if self.needs_tiebreak:
            return "tiebreak"
        return "playing"

    def resolve_tiebreak(
        self, volleys: Dict[PlayerId, Sequence[Cell]]
    ) -> TiebreakResult:
        """Разрешает «Золотой раунд» на общем поле.

        Побеждает игрок с большим числом попаданий. При полном равенстве
        общее поле пересоздаётся, и раунд нужно повторить
        (``need_repeat=True``), — повторять до расхождения.

        :raises RuntimeError: если тайбрейк не требуется или матч завершён.
        """
        if self.finished:
            raise RuntimeError("match already finished")
        if not self.needs_tiebreak:
            raise RuntimeError("tiebreak not required")

        board = self.tiebreak_board
        limit = self.config.tiebreak_shots

        hits: Dict[PlayerId, int] = {}
        shots: Dict[PlayerId, List[Cell]] = {}
        auto_filled: Dict[PlayerId, int] = {}
        to_fire: List[Cell] = []

        for p in range(self.config.players):
            chosen, filled = self._select_cells(board, volleys.get(p, ()), limit)
            shots[p] = chosen
            auto_filled[p] = filled
            hits[p] = sum(1 for c in chosen if board.is_ship_cell(c))
            to_fire.extend(chosen)

        for cell in to_fire:
            board.fire(cell)

        self.tiebreak_round += 1

        if len(set(hits.values())) == 1:
            # Полное равенство попаданий — новое общее поле и повтор раунда.
            self.tiebreak_board = self._new_tiebreak_board()
            return TiebreakResult(
                round_no=self.tiebreak_round,
                hits=hits,
                shots=shots,
                auto_filled=auto_filled,
                winner=None,
                need_repeat=True,
                finished=False,
            )

        self.winner = max(hits, key=lambda p: hits[p])
        self.needs_tiebreak = False
        self.finished = True
        return TiebreakResult(
            round_no=self.tiebreak_round,
            hits=hits,
            shots=shots,
            auto_filled=auto_filled,
            winner=self.winner,
            need_repeat=False,
            finished=True,
        )

    @staticmethod
    def _shot_view(r: ShotResult) -> dict:
        """Представление выстрела; для потопления раскрывает клетки корабля."""
        item = {"cell": list(r.cell), "outcome": r.outcome.value}
        if r.sunk_ship is not None:
            item["ship"] = [list(c) for c in r.sunk_ship]
        return item

    def view_for(self, player: PlayerId) -> dict:
        """Данные, которые безопасно показать игроку ``player``.

        Свои корабли раскрываются полностью, координаты кораблей соперника —
        нет (только уже сделанные по нему выстрелы и их исходы).
        """
        own = self.boards[player]
        enemy = self.opponent_board(player)
        return {
            "round_no": self.round_no,
            "phase": self.phase,
            "tiebreak_round": self.tiebreak_round,
            "finished": self.finished,
            "winner": self.winner,
            "draw": self.draw,
            "your_ships": [list(ship) for ship in own.ships],
            "enemy_shots": [self._shot_view(r) for r in own.shots.values()],
            "your_shots": [self._shot_view(r) for r in enemy.shots.values()],
        }
