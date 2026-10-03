"""Случайная генерация валидной расстановки флота.

Правила расстановки:
- каждый корабль целиком лежит в границах поля (rows x cols);
- корабли не соприкасаются даже углами: между клетками РАЗНЫХ кораблей
  расстояние Чебышёва строго больше 1 (это запрещает и диагональные касания).

Генерация выполняется рандомизированным backtracking, поэтому валидная
расстановка находится гарантированно, если она вообще существует.
"""
from __future__ import annotations

import random
from typing import Dict, List, Sequence, Set, Tuple

Cell = Tuple[int, int]
Ship = Tuple[Cell, ...]
Fleet = Tuple[Ship, ...]

DEFAULT_ROWS = 5
DEFAULT_COLS = 5
DEFAULT_FLEET: Tuple[int, ...] = (3, 2, 1)


def _all_placements(size: int, rows: int, cols: int) -> List[Ship]:
    """Все возможные положения корабля длины ``size`` на поле rows x cols."""
    placements: List[Ship] = []
    for r in range(rows):
        for c in range(cols):
            if c + size <= cols:
                placements.append(tuple((r, c + i) for i in range(size)))
            if size > 1 and r + size <= rows:
                placements.append(tuple((r + i, c) for i in range(size)))
    return placements


def _chebyshev(a: Cell, b: Cell) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _fits(ship: Ship, occupied: Set[Cell]) -> bool:
    """True, если корабль не пересекается и не касается уже поставленных."""
    for cell in ship:
        for placed in occupied:
            if _chebyshev(cell, placed) <= 1:
                return False
    return True


def generate_fleet(
    rows: int = DEFAULT_ROWS,
    cols: int = DEFAULT_COLS,
    fleet: Sequence[int] = DEFAULT_FLEET,
    rng: random.Random | None = None,
) -> Fleet:
    """Возвращает валидную расстановку кораблей.

    :param rows: число строк поля.
    :param cols: число столбцов поля.
    :param fleet: длины кораблей (по умолчанию трёх-, двух- и однопалубный).
    :param rng: источник случайности (удобно для тестов с фиксированным seed).
    :raises ValueError: если расстановку невозможно разместить.
    """
    rng = rng or random.Random()
    sizes = tuple(sorted(fleet, reverse=True))
    if not sizes:
        raise ValueError("fleet must not be empty")

    placements_by_size: Dict[int, List[Ship]] = {
        size: _all_placements(size, rows, cols) for size in set(sizes)
    }
    # Перемешиваем один раз на каждый размер — этого достаточно для рандома.
    for size, placements in placements_by_size.items():
        if not placements:
            raise ValueError(
                f"ship of size {size} does not fit on {rows}x{cols} board"
            )
        rng.shuffle(placements)

    occupied: Set[Cell] = set()
    chosen: List[Ship] = []

    def backtrack(index: int) -> bool:
        if index == len(sizes):
            return True
        size = sizes[index]
        for ship in placements_by_size[size]:
            if _fits(ship, occupied):
                occupied.update(ship)
                chosen.append(ship)
                if backtrack(index + 1):
                    return True
                chosen.pop()
                occupied.difference_update(ship)
        return False

    if not backtrack(0):
        raise ValueError(
            f"cannot place fleet {sizes} on {rows}x{cols} board"
        )
    return tuple(chosen)


def fleet_cells(fleet: Fleet) -> Set[Cell]:
    """Множество всех занятых кораблями клеток."""
    return {cell for ship in fleet for cell in ship}


def ships_are_disconnected(fleet: Fleet) -> bool:
    """True, если корабли не соприкасаются даже углами."""
    for i in range(len(fleet)):
        for j in range(i + 1, len(fleet)):
            for a in fleet[i]:
                for b in fleet[j]:
                    if _chebyshev(a, b) <= 1:
                        return False
    return True
