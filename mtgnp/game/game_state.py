from dataclasses import dataclass, field
from .player import PlayerState


@dataclass
class GameState:
    phase: str = "LOBBY"

    players: dict[str, PlayerState] = field(
        default_factory=dict
    )

    turn: int = 0
    active_player: str | None = None
    priority_player: str | None = None
    priority_seq_num: int = 0

    stack: list[dict] = field(default_factory=list)

    game_over: bool = False
    winner: str | None = None
    game_over_reason: str | None = None