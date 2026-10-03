"""Оценка тайбрейк-раунда ('Golden round') для обоюдного KO.

Варианты:
  A1 beacon     — 1 выстрел по общей СКРЫТОЙ клетке, побеждает ближний.
  shared-fresh  — общее поле с флотом 3+2+1, оба бьют 3 раза, побеждает тот,
                  у кого больше попаданий; при равенстве — НОВОЕ общее поле.
  shared-same   — то же, но повтор на ТОМ ЖЕ поле (демонстрация проблемы
                  бесконечного цикла, когда весь флот уже расстрелян).

Печатает среднее число тайбрейк-раундов и долю, решённых с первого раза.
"""
from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path
from typing import List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.game.board import Board  # noqa: E402
from app.game.fleet import DEFAULT_FLEET, generate_fleet  # noqa: E402

Cell = Tuple[int, int]
ROWS = COLS = 5
SHOTS = 3
N = 5000


def neighbors(cell: Cell) -> List[Cell]:
    r, c = cell
    out = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < ROWS and 0 <= nc < COLS:
            out.append((nr, nc))
    return out


def smart_picks(board: Board, rng: random.Random, shots: int) -> List[Cell]:
    """Умный выбор: приоритет — клетки рядом с известными попаданиями."""
    unfired: Set[Cell] = set(board.unfired_cells())
    hits = [c for c, s in board.shots.items() if s.outcome.value != "miss"]
    cand: List[Cell] = []
    for h in hits:
        cand.extend(nb for nb in neighbors(h) if nb in unfired)
    rng.shuffle(cand)
    picks: List[Cell] = []
    seen: Set[Cell] = set()
    for c in cand:
        if c not in seen:
            seen.add(c)
            picks.append(c)
        if len(picks) == shots:
            return picks
    pool = list(unfired - seen)
    rng.shuffle(pool)
    while len(picks) < shots and pool:
        picks.append(pool.pop())
    return picks


def fresh_board(rng: random.Random) -> Board:
    return Board(generate_fleet(ROWS, COLS, DEFAULT_FLEET, rng), ROWS, COLS)


def shared_fresh(rng: random.Random, shots: int) -> bool:
    """True, если раунд нужно повторить (равное число попаданий)."""
    board = fresh_board(rng)
    a = smart_picks(board, rng, shots)
    b = smart_picks(board, rng, shots)
    hits_a = sum(board.is_ship_cell(c) for c in a)
    hits_b = sum(board.is_ship_cell(c) for c in b)
    return hits_a == hits_b


def shared_same(rng: random.Random) -> int:
    """Число раундов до расхождения, либо очень большое (ограничение сверху)."""
    board = fresh_board(rng)
    for _ in range(100):
        a = smart_picks(board, rng, SHOTS)
        b = smart_picks(board, rng, SHOTS)
        hits_a = sum(board.is_ship_cell(c) for c in a)
        hits_b = sum(board.is_ship_cell(c) for c in b)
        for c in set(a) | set(b):
            board.fire(c)
        if hits_a != hits_b:
            return _
    return 100


def beacon(rng: random.Random) -> bool:
    target = (rng.randrange(ROWS), rng.randrange(COLS))
    a = (rng.randrange(ROWS), rng.randrange(COLS))
    b = (rng.randrange(ROWS), rng.randrange(COLS))

    def d(c):
        return abs(c[0] - target[0]) + abs(c[1] - target[1])

    return d(a) == d(b)


def simulate_repeat(fn, name: str, shots: int) -> None:
    lens: Counter[int] = Counter()
    for _ in range(N):
        rng = random.Random(random.random())
        rounds = 1
        while fn(rng, shots):
            rounds += 1
        lens[rounds] += 1
    total = sum(lens.values())
    avg = sum(k * v for k, v in lens.items()) / total
    print(f"{name:<16} shots={shots}  avg rounds = {avg:.3f} | "
          f"с первого раза = {100 * lens[1] / total:5.1f}%")


print(f"n = {N} (умный выбор выстрелов)")
simulate_repeat(shared_fresh, "shared-fresh", 3)
simulate_repeat(shared_fresh, "shared-fresh", 4)
simulate_repeat(shared_fresh, "shared-fresh", 5)

# shared-same: покажем сколько раз не разошлись за 100 раундов
lens: Counter[int] = Counter()
for _ in range(1000):
    lens[shared_same(random.Random(random.random()))] += 1
print(f"shared-same     не разошлись за 100 раундов: {lens[100]}/1000 случаев")
