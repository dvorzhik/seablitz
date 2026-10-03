"""Чистое игровое ядро «Морского блица» (без сети и Telegram)."""

from .board import Board, ShotOutcome, ShotResult
from .fleet import (
    DEFAULT_COLS,
    DEFAULT_FLEET,
    DEFAULT_ROWS,
    Cell,
    Fleet,
    Ship,
    fleet_cells,
    generate_fleet,
    ships_are_disconnected,
)
from .match import (
    Match,
    MatchConfig,
    PlayerRoundReport,
    RoundResult,
    TiebreakResult,
)

__all__ = [
    "Board",
    "ShotOutcome",
    "ShotResult",
    "DEFAULT_COLS",
    "DEFAULT_FLEET",
    "DEFAULT_ROWS",
    "Cell",
    "Fleet",
    "Ship",
    "fleet_cells",
    "generate_fleet",
    "ships_are_disconnected",
    "Match",
    "MatchConfig",
    "PlayerRoundReport",
    "RoundResult",
    "TiebreakResult",
]
