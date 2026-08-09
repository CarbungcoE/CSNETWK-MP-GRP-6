from enum import Enum, auto
from typing import List, Set, Dict, Any, Optional


class PriorityResult(Enum):
    """Result of a priority pass action."""
    NEXT_PLAYER = auto()             # Priority passed to the next player in turn order
    RESOLVE_STACK = auto()           # All players passed in succession; top of stack resolves
    ADVANCE_STEP = auto()            # All players passed in succession with empty stack; advance phase/step


class PriorityManager:
    """
    Manages player priority, turn order sequence, and phase state transitions.
    
    Key Rules (MTG CR 117):
    - Active Player (AP) receives priority at the start of steps/phases (CR 117.3a).
    - AP receives priority after a spell/ability resolves or is placed on the stack (CR 117.3b).
    - Passing priority shifts priority to the next player in turn order (CR 117.3d).
    - If all players pass in succession without taking actions:
        * Stack is non-empty -> Top item resolves (CR 117.4).
        * Stack is empty -> Current step/phase ends (CR 117.4).
    """

    def __init__(self, players: List[str], active_player_index: int = 0):
        if not players:
            raise ValueError("Player list cannot be empty.")
            
        self.players: List[str] = list(players)
        self.active_player_index: int = active_player_index
        self.priority_holder_index: int = active_player_index
        self._passed_players: Set[str] = set()

    @property
    def active_player(self) -> str:
        """Returns the current Active Player ID."""
        return self.players[self.active_player_index]

    @property
    def current_holder(self) -> str:
        """Returns the player ID who currently holds priority."""
        return self.players[self.priority_holder_index]

    def reset_priority_to_active(self) -> None:
        """Grants priority to the active player and resets all priority passes."""
        self.priority_holder_index = self.active_player_index
        self._passed_players.clear()

    def grant_priority(self, player_id: str) -> None:
        """Explicitly assigns priority to a specific player and resets passes."""
        if player_id not in self.players:
            raise ValueError(f"Player '{player_id}' is not in the active game session.")
        self.priority_holder_index = self.players.index(player_id)
        self._passed_players.clear()

    def pass_priority(self, player_id: str, is_stack_empty: bool) -> PriorityResult:
        """
        Processes a pass priority action from a player.

        Args:
            player_id: The ID of the player attempting to pass priority.
            is_stack_empty: Boolean indicating if the stack currently contains no objects.

        Returns:
            PriorityResult: Dictates if priority shifts, stack resolves, or phase advances.
        """
        if player_id != self.current_holder:
            raise ValueError(f"Action invalid: Player '{player_id}' does not hold priority.")

        self._passed_players.add(player_id)

        # Check if all active players in the match have passed in succession
        if len(self._passed_players) >= len(self.players):
            self._passed_players.clear()
            # Active player receives priority after stack resolution or phase move
            self.priority_holder_index = self.active_player_index
            
            if is_stack_empty:
                return PriorityResult.ADVANCE_STEP
            return PriorityResult.RESOLVE_STACK

        # Rotate priority to the next player in turn order
        self.priority_holder_index = (self.priority_holder_index + 1) % len(self.players)
        return PriorityResult.NEXT_PLAYER

    def on_action(self, player_id: str) -> None:
        """
        Must be called when a player takes an action requiring priority 
        (casting a spell, activating an ability, or playing a land).
        
        Resets passing history. The acting player retains priority (CR 117.3c).
        """
        if player_id != self.current_holder:
            raise ValueError(f"Action invalid: Player '{player_id}' acted without priority.")
        
        self._passed_players.clear()

    def set_next_turn(self, next_active_player_id: Optional[str] = None) -> None:
        """Advances active player for a new turn."""
        if next_active_player_id:
            if next_active_player_id not in self.players:
                raise ValueError(f"Player '{next_active_player_id}' not found.")
            self.active_player_index = self.players.index(next_active_player_id)
        else:
            self.active_player_index = (self.active_player_index + 1) % len(self.players)
            
        self.reset_priority_to_active()

    def remove_player(self, player_id: str) -> None:
        """Handles player elimination or disconnection during priority tracking."""
        if player_id not in self.players:
            return

        idx = self.players.index(player_id)
        self.players.remove(player_id)
        self._passed_players.discard(player_id)

        if not self.players:
            return

        # Adjust indices if necessary
        if self.active_player_index >= len(self.players):
            self.active_player_index = 0
            
        if self.priority_holder_index >= len(self.players):
            self.priority_holder_index = self.priority_holder_index % len(self.players)