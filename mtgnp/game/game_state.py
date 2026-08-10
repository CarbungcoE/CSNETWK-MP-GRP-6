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
    consecutive_passes: int = 0

    # Sequence number of the latest authoritative
    # GAME_STATE_UPDATE sent by the server.
    server_seq_num: int = 0

    # Sequence number expected from the client for the
    # currently pending action.
    priority_seq_num: int = 0

    # MULLIGAN_CHOICE is keyed to the GAME_STATE_UPDATE
    # that opened the mulligan window, not priority.
    mulligan_seq_nums: dict[str, int] = field(
        default_factory=dict
    )

    stack: list[dict] = field(
        default_factory=list
    )

    game_over: bool = False
    winner: str | None = None
    game_over_reason: str | None = None