from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


class Step(Enum):
    UNTAP = "untap"
    UPKEEP = "upkeep"
    DRAW = "draw"
    MAIN_1 = "main_1"
    BEGIN_COMBAT = "begin_combat"
    DECLARE_ATTACKERS = "declare_attackers"
    DECLARE_BLOCKERS = "declare_blockers"
    COMBAT_DAMAGE = "combat_damage"
    END_COMBAT = "end_combat"
    MAIN_2 = "main_2"
    END_STEP = "end_step"
    CLEANUP = "cleanup"


STEP_ORDER = [
    Step.UNTAP,
    Step.UPKEEP,
    Step.DRAW,
    Step.MAIN_1,
    Step.BEGIN_COMBAT,
    Step.DECLARE_ATTACKERS,
    Step.DECLARE_BLOCKERS,
    Step.COMBAT_DAMAGE,
    Step.END_COMBAT,
    Step.MAIN_2,
    Step.END_STEP,
    Step.CLEANUP,
]


class TurnEngine:
    """
    Manages turn order, active player focus, phase/step state transitions,
    and priority progression for an MTG match.
    """
    def __init__(self, players: List[str]):
        if not players:
            raise ValueError("TurnEngine requires at least one player.")
        
        self.players: List[str] = players
        self.turn_number: int = 1
        self.active_player_index: int = 0
        self.step_index: int = 0
        self.priority_player_index: int = 0
        self.extra_turns: List[str] = []

    @property
    def active_player(self) -> str:
        """Returns the player whose turn it currently is."""
        return self.players[self.active_player_index]

    @property
    def priority_player(self) -> str:
        """Returns the player who currently has priority to cast spells/abilities."""
        return self.players[self.priority_player_index]

    @property
    def current_step(self) -> Step:
        """Returns the current step in the turn sequence."""
        return STEP_ORDER[self.step_index]

    def advance_step(self) -> Step:
        """
        Advances to the next step in the sequence.
        If the cleanup step finishes, transitions to the next turn.
        """
        self.step_index += 1

        if self.step_index >= len(STEP_ORDER):
            self._start_next_turn()
        else:
            self._on_step_begin()

        return self.current_step

    def pass_priority_to_next(self) -> str:
        """Passes priority clockwise to the next active player."""
        self.priority_player_index = (self.priority_player_index + 1) % len(self.players)
        return self.priority_player

    def reset_priority_to_active(self) -> None:
        """Resets priority to the active player (e.g., after an action or step change)."""
        self.priority_player_index = self.active_player_index

    def add_extra_turn(self, player_id: str) -> None:
        """Enqueues an extra turn for a specific player."""
        if player_id in self.players:
            self.extra_turns.append(player_id)

    def _start_next_turn(self) -> None:
        """Handles turn rollover mechanics and extra turn resolution."""
        self.turn_number += 1
        self.step_index = 0

        if self.extra_turns:
            next_player = self.extra_turns.pop(0)
            self.active_player_index = self.players.index(next_player)
        else:
            self.active_player_index = (self.active_player_index + 1) % len(self.players)

        self.reset_priority_to_active()
        self._on_step_begin()

    def _on_step_begin(self) -> None:
        """
        Executes turn actions specific to step entry (e.g., reset priority).
        Steps like Untap automatically advance unless triggers occur.
        """
        self.reset_priority_to_active()

        # Untap step does not give priority under normal rules
        if self.current_step == Step.UNTAP:
            self.advance_step()

    def serialize(self) -> Dict[str, Any]:
        """Returns a network-ready dictionary representation of the turn state."""
        return {
            "turn_number": self.turn_number,
            "active_player": self.active_player,
            "priority_player": self.priority_player,
            "current_step": self.current_step.value,
            "step_index": self.step_index,
            "extra_turns_queued": len(self.extra_turns),
        }