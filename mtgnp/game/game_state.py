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

    # Sequence number for priority tokens.
    #
    # This is a SEPARATE sequence domain from server_seq_num.
    priority_seq_num: int = 0

    # Sequence number of the latest authoritative
    # GAME_STATE_UPDATE sent by the server.
    #
    # MULLIGAN_CHOICE echoes this number.
    server_seq_num: int = 0

    # Number of consecutive priority passes in the current
    # priority window.
    consecutive_passes: int = 0

    stack: list[dict] = field(default_factory=list)

    game_over: bool = False
    winner: str | None = None
    game_over_reason: str | None = None