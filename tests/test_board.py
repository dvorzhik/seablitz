"""Тесты состояния поля и обработки выстрелов."""
from __future__ import annotations

import pytest

from app.game.board import Board, ShotOutcome

SHIPS = [((0, 0), (0, 1), (0, 2)), ((2, 0), (2, 1)), ((4, 4),)]


def make_board() -> Board:
    return Board(SHIPS, rows=5, cols=5)


def test_miss():
    result = make_board().fire((1, 1))
    assert result.outcome is ShotOutcome.MISS
    assert result.sunk_ship is None


def test_hit_then_sunk():
    board = make_board()
    assert board.fire((0, 0)).outcome is ShotOutcome.HIT
    assert board.fire((0, 1)).outcome is ShotOutcome.HIT
    result = board.fire((0, 2))
    assert result.outcome is ShotOutcome.SUNK
    assert result.sunk_ship == ((0, 0), (0, 1), (0, 2))


def test_refire_is_idempotent():
    board = make_board()
    first = board.fire((0, 0))
    second = board.fire((0, 0))
    assert first == second
    assert len(board.shots) == 1


def test_out_of_bounds_raises():
    board = make_board()
    with pytest.raises(ValueError):
        board.fire((5, 0))
    with pytest.raises(ValueError):
        board.fire((0, -1))


def test_all_sunk():
    board = make_board()
    assert not board.all_sunk()
    for ship in SHIPS:
        for cell in ship:
            board.fire(cell)
    assert board.all_sunk()


def test_unfired_cells():
    board = make_board()
    board.fire((0, 0))
    assert (0, 0) not in board.unfired_cells()
    assert len(board.unfired_cells()) == 24
