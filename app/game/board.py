"""Состояние поля одного игрока и обработка выстрелов."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from .fleet import Cell, Ship


class ShotOutcome(str, Enum):
    """Результат одного выстрела."""

    MISS = "miss"
    HIT = "hit"
    SUNK = "sunk"


@dataclass(frozen=True)
class ShotResult:
    """Результат выстрела: клетка, исход и потопленный корабль (если есть)."""

    cell: Cell
    outcome: ShotOutcome
    sunk_ship: Optional[Ship] = None


class Board:
    """Поле игрока: хранит корабли и уже сделанные по нему выстрелы."""

    def __init__(self, ships: Sequence[Ship], rows: int = 5, cols: int = 5):
        self.rows = rows
        self.cols = cols
        self.ships: Tuple[Ship, ...] = tuple(tuple(ship) for ship in ships)

        self._ship_of: Dict[Cell, int] = {}
        for index, ship in enumerate(self.ships):
            for cell in ship:
                self._ship_of[cell] = index

        self._hits_per_ship: List[int] = [0] * len(self.ships)
        self._shots: Dict[Cell, ShotResult] = {}

    def in_bounds(self, cell: Cell) -> bool:
        r, c = cell
        return 0 <= r < self.rows and 0 <= c < self.cols

    def is_ship_cell(self, cell: Cell) -> bool:
        return cell in self._ship_of

    def already_shot(self, cell: Cell) -> bool:
        return cell in self._shots

    @property
    def shots(self) -> Dict[Cell, ShotResult]:
        """Копия карты сделанных выстрелов: клетка -> результат."""
        return dict(self._shots)

    def fire(self, cell: Cell) -> ShotResult:
        """Обрабатывает выстрел по клетке.

        Идемпотентно: повторный выстрел по уже обстрелянной клетке
        возвращает ранее вычисленный результат и не меняет состояние.

        :raises ValueError: если клетка вне поля.
        """
        if not self.in_bounds(cell):
            raise ValueError(f"cell {cell} out of bounds")

        cached = self._shots.get(cell)
        if cached is not None:
            return cached

        sunk_ship: Optional[Ship] = None
        if cell in self._ship_of:
            index = self._ship_of[cell]
            self._hits_per_ship[index] += 1
            ship = self.ships[index]
            if self._hits_per_ship[index] == len(ship):
                outcome = ShotOutcome.SUNK
                sunk_ship = ship
            else:
                outcome = ShotOutcome.HIT
        else:
            outcome = ShotOutcome.MISS

        result = ShotResult(cell=cell, outcome=outcome, sunk_ship=sunk_ship)
        self._shots[cell] = result
        return result

    def ship_is_sunk(self, index: int) -> bool:
        return self._hits_per_ship[index] == len(self.ships[index])

    def all_sunk(self) -> bool:
        """True, если потоплены все корабли флота."""
        return all(
            self.ship_is_sunk(i) for i in range(len(self.ships))
        )

    def all_cells(self) -> List[Cell]:
        return [(r, c) for r in range(self.rows) for c in range(self.cols)]

    def unfired_cells(self) -> List[Cell]:
        """Клетки, по которым ещё не стреляли."""
        return [cell for cell in self.all_cells() if cell not in self._shots]
