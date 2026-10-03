"""Тесты матча: одновременные залпы, автодобивание, ничья и победитель."""
from __future__ import annotations

import random

import pytest

from app.game.match import Match, MatchConfig


def make_match(**config_kwargs) -> Match:
    config = MatchConfig(**config_kwargs)
    return Match(config=config, rng=random.Random(123))


def test_empty_volley_is_auto_filled():
    result = make_match().resolve_round({0: [], 1: []})
    assert len(result.players[0].shots) == 3
    assert result.players[0].auto_filled == 3
    assert len(result.players[1].shots) == 3
    assert result.players[1].auto_filled == 3


def test_volley_is_capped_and_deduped():
    volley = [(0, 0), (0, 0), (1, 1), (2, 2), (3, 3)]
    result = make_match().resolve_round({0: volley, 1: []})
    cells = [s.cell for s in result.players[0].shots]
    assert len(cells) == 3
    assert len(set(cells)) == 3


def test_auto_fill_skips_already_shot_cells():
    match = make_match()
    first = match.resolve_round({0: [(0, 0)], 1: []})
    used = {s.cell for s in first.players[0].shots}
    assert len(used) == 3

    second = match.resolve_round({0: [(0, 0)], 1: []})
    cells2 = {s.cell for s in second.players[0].shots}
    assert (0, 0) not in cells2
    assert cells2.isdisjoint(used)


def _double_ko_match(seed: int = 0, tiebreak_shots: int = 3) -> Match:
    """Матч, доведённый до обоюдного KO (оба флота по 1 клетке)."""
    match = Match(
        config=MatchConfig(
            fleet=(1,), shots_per_round=1, tiebreak_shots=tiebreak_shots
        ),
        rng=random.Random(seed),
        fleets={0: [((0, 0),)], 1: [((0, 0),)]},
    )
    result = match.resolve_round({0: [(0, 0)], 1: [(0, 0)]})
    assert result.needs_tiebreak
    return match


def test_double_ko_enters_tiebreak():
    match = _double_ko_match()
    assert match.needs_tiebreak
    assert not match.finished
    assert match.phase == "tiebreak"
    assert match.tiebreak_board is not None


def test_double_ko_never_reports_draw():
    result = Match(
        config=MatchConfig(fleet=(1,), shots_per_round=1),
        rng=random.Random(0),
        fleets={0: [((0, 0),)], 1: [((0, 0),)]},
    ).resolve_round({0: [(0, 0)], 1: [(0, 0)]})
    assert not result.draw
    assert not result.finished
    assert result.needs_tiebreak


def test_resolve_round_forbidden_during_tiebreak():
    match = _double_ko_match()
    with pytest.raises(RuntimeError):
        match.resolve_round({0: [], 1: []})


def test_tiebreak_not_required_raises():
    match = Match(config=MatchConfig(), rng=random.Random(0))
    with pytest.raises(RuntimeError):
        match.resolve_tiebreak({0: [], 1: []})


def test_tiebreak_winner_by_hits():
    match = _double_ko_match(seed=1, tiebreak_shots=1)
    board = match.tiebreak_board
    ship = next(c for c in board.all_cells() if board.is_ship_cell(c))
    water = next(c for c in board.all_cells() if not board.is_ship_cell(c))
    result = match.resolve_tiebreak({0: [ship], 1: [water]})
    assert result.hits == {0: 1, 1: 0}
    assert result.winner == 0
    assert result.finished and not result.need_repeat
    assert match.phase == "finished"


def test_tiebreak_repeat_on_fresh_board():
    match = _double_ko_match(seed=2, tiebreak_shots=1)
    board = match.tiebreak_board
    water = [c for c in board.all_cells() if not board.is_ship_cell(c)]
    result = match.resolve_tiebreak({0: [water[0]], 1: [water[1]]})
    assert result.hits == {0: 0, 1: 0}
    assert result.need_repeat and not result.finished
    assert match.needs_tiebreak
    assert match.tiebreak_round == 1

    new_board = match.tiebreak_board
    assert new_board is not board  # поле пересоздано

    ship = next(c for c in new_board.all_cells() if new_board.is_ship_cell(c))
    other_water = next(
        c for c in new_board.all_cells() if not new_board.is_ship_cell(c)
    )
    res2 = match.resolve_tiebreak({0: [ship], 1: [other_water]})
    assert res2.finished and res2.winner == 0
    assert match.tiebreak_round == 2


def test_tiebreak_eventually_finishes():
    match = _double_ko_match(seed=5)
    result = None
    for _ in range(1000):
        result = match.resolve_tiebreak({0: [], 1: []})
        if result.finished:
            break
    assert result is not None and result.finished
    assert match.winner in (0, 1)


def test_out_of_bounds_shot_is_ignored():
    result = make_match().resolve_round({0: [(9, 9)], 1: []})
    assert (9, 9) not in {s.cell for s in result.players[0].shots}
    assert len(result.players[0].shots) == 3


def test_match_always_ends_with_a_winner():
    # Матч не может закончиться ничьей: при обоюдном KO включается тайбрейк.
    match = Match(config=MatchConfig(), rng=random.Random(11))
    for _ in range(200):
        if match.finished:
            break
        if match.needs_tiebreak:
            match.resolve_tiebreak({0: [], 1: []})
        else:
            match.resolve_round({0: [], 1: []})
    assert match.finished
    assert match.winner in (0, 1)
    assert not match.draw


def test_winner_is_determined():
    match = Match(
        config=MatchConfig(fleet=(1,), shots_per_round=1),
        rng=random.Random(0),
        fleets={0: [((0, 0),)], 1: [((4, 4),)]},
    )
    # игрок 0 топит единственный корабль соперника, игрок 1 мажет
    result = match.resolve_round({0: [(4, 4)], 1: [(1, 1)]})
    assert result.winner == 0
    assert not result.draw
    assert result.finished


def test_resolve_after_finish_raises():
    match = Match(
        config=MatchConfig(fleet=(1,), shots_per_round=1),
        rng=random.Random(0),
        fleets={0: [((0, 0),)], 1: [((0, 0),)]},
    )
    match.resolve_round({0: [(0, 0)], 1: [(0, 0)]})
    with pytest.raises(RuntimeError):
        match.resolve_round({0: [], 1: []})


def test_view_reveals_sunk_ship_cells():
    match = Match(
        config=MatchConfig(fleet=(2,), shots_per_round=3),
        rng=random.Random(0),
        fleets={0: [((0, 0),)], 1: [((0, 0), (0, 1))]},
    )
    # игрок 0 топит двухпалубный корабль игрока 1
    match.resolve_round({0: [(0, 0), (0, 1)], 1: []})
    view = match.view_for(0)
    sunk = [s for s in view["your_shots"] if s["outcome"] == "sunk"]
    assert sunk, view["your_shots"]
    assert sunk[0]["ship"] == [[0, 0], [0, 1]]


def test_view_for_hides_enemy_ships():
    match = make_match()
    match.resolve_round({0: [(0, 0), (0, 1), (0, 2)], 1: []})
    view = match.view_for(0)
    assert len(view["your_ships"]) == 3
    assert view["round_no"] == 1
    # в представлении нет координат вражеских кораблей, только выстрелы
    assert "enemy_ships" not in view
    assert len(view["your_shots"]) == 3
