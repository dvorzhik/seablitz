"""Инструмент для оценки баланса «Морского блица».

Прогоняет N партий для разных конфигов и печатает среднее число раундов,
доля ничьих и доля партий, уложившихся в 5 раундов. Помогает подбирать
shots_per_round / состав флота под целевой темп партии.

Запуск:
    python scripts/balance_sim.py
    python scripts/balance_sim.py --n 5000
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path
from typing import List, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.game.match import Match, MatchConfig  # noqa: E402

Cell = Tuple[int, int]

CONFIGS = [
    ("3 shots, 3+2+1", 3, (3, 2, 1)),
    ("4 shots, 3+2+1", 4, (3, 2, 1)),
    ("5 shots, 3+2+1", 5, (3, 2, 1)),
    ("3 shots, 2+2+1", 3, (2, 2, 1)),
    ("4 shots, 2+2+1", 4, (2, 2, 1)),
    ("3 shots, 2+1", 3, (2, 1)),
    ("4 shots, 2+1", 4, (2, 1)),
    ("5 shots, 2+1", 5, (2, 1)),
]


def neighbors(cell: Cell, rows: int, cols: int) -> List[Cell]:
    r, c = cell
    out: List[Cell] = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def play(strategy: str, seed: int, shots: int, fleet: Sequence[int]):
    """Одна партия. Стратегия 'smart' добивает клетки рядом с попаданиями."""
    rng = random.Random(seed)
    cfg = MatchConfig(shots_per_round=shots, fleet=tuple(fleet))
    match = Match(config=cfg, rng=rng)
    rounds = 0
    while not match.finished:
        rounds += 1
        volleys = {}
        for p in (0, 1):
            board = match.opponent_board(p)
            unfired: Set[Cell] = set(board.unfired_cells())
            picks: List[Cell] = []
            if strategy == "smart":
                hits = [
                    c for c, s in board.shots.items() if s.outcome.value != "miss"
                ]
                candidates: List[Cell] = []
                for h in hits:
                    candidates.extend(
                        nb for nb in neighbors(h, cfg.rows, cfg.cols) if nb in unfired
                    )
                rng.shuffle(candidates)
                for c in candidates:
                    if c not in picks:
                        picks.append(c)
                    if len(picks) == cfg.shots_per_round:
                        break
            pool = list(unfired - set(picks))
            rng.shuffle(pool)
            while len(picks) < cfg.shots_per_round and pool:
                picks.append(pool.pop())
            volleys[p] = picks
        match.resolve_round(volleys)
    return rounds, match.draw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=3000, help="число партий на конфиг")
    parser.add_argument(
        "--strategy", choices=("random", "smart"), default="smart"
    )
    args = parser.parse_args()

    print(f"strategy={args.strategy}, n={args.n} per config")
    print(f"{'config':<18}{'avg rounds':>12}{'draw %':>9}{'<=5 rounds %':>14}")
    for name, shots, fleet in CONFIGS:
        lens: Counter[int] = Counter()
        draws = 0
        for i in range(args.n):
            r, d = play(args.strategy, i, shots, fleet)
            lens[r] += 1
            draws += int(d)
        total = sum(lens.values())
        avg = sum(k * v for k, v in lens.items()) / total
        le5 = sum(v for k, v in lens.items() if k <= 5) / total
        print(f"{name:<18}{avg:>12.2f}{100 * draws / total:>8.0f}%{100 * le5:>13.0f}%")


if __name__ == "__main__":
    main()
