"""Тесты генерации расстановки флота."""
from __future__ import annotations

import random

import pytest

from app.game.fleet import (
    DEFAULT_COLS,
    DEFAULT_FLEET,
    DEFAULT_ROWS,
    fleet_cells,
    generate_fleet,
    ships_are_disconnected,
)


def test_default_fleet_sizes():
    fleet = generate_fleet(rng=random.Random(1))
    assert sorted((len(s) for s in fleet), reverse=True) == sorted(
        DEFAULT_FLEET, reverse=True
    )


def test_occupied_cell_count():
    fleet = generate_fleet(rng=random.Random(2))
    assert len(fleet_cells(fleet)) == sum(DEFAULT_FLEET)


@pytest.mark.parametrize("seed", range(200))
def test_placement_is_valid(seed):
    fleet = generate_fleet(rng=random.Random(seed))
    cells = fleet_cells(fleet)

    # нет пересечений между кораблями
    assert len(cells) == sum(len(s) for s in fleet)

    # всё внутри поля
    for r, c in cells:
        assert 0 <= r < DEFAULT_ROWS
        assert 0 <= c < DEFAULT_COLS

    # корабли не соприкасаются даже углами
    assert ships_are_disconnected(fleet)

    # каждый корабль — прямая линия (одна строка или один столбец)
    for ship in fleet:
        rows = {r for r, _ in ship}
        cols = {c for _, c in ship}
        assert len(rows) == 1 or len(cols) == 1


def test_deterministic_for_same_seed():
    assert generate_fleet(rng=random.Random(42)) == generate_fleet(
        rng=random.Random(42)
    )


def test_raises_when_ship_does_not_fit():
    with pytest.raises(ValueError):
        generate_fleet(rows=2, cols=2, fleet=(3,), rng=random.Random(0))


def test_empty_fleet_raises():
    with pytest.raises(ValueError):
        generate_fleet(fleet=(), rng=random.Random(0))


def test_custom_fleet_on_larger_board():
    fleet = generate_fleet(rows=6, cols=6, fleet=(3, 2, 1), rng=random.Random(7))
    assert sorted(len(s) for s in fleet) == [1, 2, 3]
    assert ships_are_disconnected(fleet)
