from dataclasses import dataclass, field


@dataclass
class PlayerState:
    player_id: str

    deck: list[str] = field(default_factory=list)
    library: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)

    battlefield: list[dict] = field(default_factory=list)
    graveyard: list[dict] = field(default_factory=list)

    life: int = 20

    mulligan_count: int = 0
    kept_hand: bool = False

    land_played_this_turn: bool = False