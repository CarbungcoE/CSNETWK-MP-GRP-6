from mtgnp.game.game_state import GameState
from mtgnp.game.lifecycle import GameLifecycle
from mtgnp.game.turn import TurnEngine
from mtgnp.game.priority import PriorityManager
from mtgnp.game.stack import StackManager
from mtgnp.game.combat import CombatSystem

class GameSession:
    """
    Represents one authoritative game session.

    GameSession owns the single GameState instance and provides
    access to the systems that operate on that state.
    """

    def __init__(self):
      self.state = GameState()

      self.lifecycle = GameLifecycle(self.state)
      self.priority = PriorityManager(self.state)
      self.turn = TurnEngine(
        self.state,
        self.priority
      )
      self.stack = StackManager(self.state)
      self.combat = CombatSystem(self.state)

    def player_ready(
        self,
        player_id: str,
        deck_list: list,
    ) -> tuple[bool, str, dict]:
        """
        Process a PLAYER_READY request through the game lifecycle.

        Returns:
            (success, error_code, lobby_state)
        """
        return self.lifecycle.process_player_ready(
            player_id,
            deck_list,
        )

    def start_setup(self):
        """
        Begin automated game setup.
        """
        self.lifecycle.setup_game()

    def process_mulligan(
        self,
        player_id: str,
        keep: bool,
        cards_to_bottom: list,
    ):
        """
        Process a player's mulligan decision.
        """
        success, error = self.lifecycle.process_mulligan(
            player_id,
            keep,
            cards_to_bottom,
        )

        if (
            success
            and self.lifecycle.is_mulligan_complete()
            and self.state.phase == "MULLIGAN"
        ):
            self.turn.start_game()

        return success, error

    def is_mulligan_complete(self) -> bool:
        """
        Check whether all players have kept their opening hands.
        """
        return self.lifecycle.is_mulligan_complete()

    def get_visible_state(self, player_id: str):
        """
        Generate the state visible to a specific player.
        """
        return self.lifecycle.generate_visible_state(
            player_id
        )

    def start_game(self) -> None:
      """
      Start the first turn after the mulligan phase.
      """
      self.turn.start_game()


    def begin_turn(self) -> None:
        """
        Begin a new turn.
        """
        self.turn.begin_turn()


    def advance_phase(self) -> str:
        """
        Advance to the next phase.
        """
        return self.turn.advance_phase()

    def grant_priority(self, player_id: str) -> int:
        """
        Grant priority to a player.
        """
        return self.priority.grant_priority(player_id)


    def pass_priority(self) -> str | None:
        """
        Pass priority to the other player.
        """
        return self.priority.pass_priority()


    def grant_active_player_priority(self) -> str:
        """
        Grant priority to the active player.
        """
        return self.priority.grant_active_player_priority()


    def has_priority(self, player_id: str) -> bool:
        """
        Check whether a player currently has priority.
        """
        return self.priority.has_priority(player_id)

    def get_priority_seq_num(self) -> int:
        """
        Return the current authoritative priority sequence number.
        """
        return self.state.priority_seq_num

    def validate_priority_seq_num(self, seq_num: int) -> bool:
        """
        Validate a client's priority sequence number.
        """
        return self.priority.validate_seq_num(seq_num)

    def push_stack(self, item: dict) -> None:
      """
      Put an object onto the game stack.
      """
      self.stack.push(item)


    def pop_stack(self) -> dict | None:
        """
        Remove and return the top stack object.
        """
        return self.stack.pop()


    def peek_stack(self) -> dict | None:
        """
        Inspect the top stack object without removing it.
        """
        return self.stack.peek()


    def resolve_stack(self) -> dict | None:
        """
        Remove the top object from the stack for resolution.
        """
        return self.stack.resolve_top()
    
    def declare_attackers(self, player_id: str, attackers: list):
      """
      Declare attackers for the active player.
      """
      return self.combat.declare_attackers(
          player_id,
          attackers,
      )


    def declare_blockers(self, player_id: str, blockers: list):
        """
        Declare blockers for the defending player.
        """
        return self.combat.declare_blockers(
            player_id,
            blockers,
        )


    def check_damage_order_needed(self):
        """
        Determine which attackers require damage ordering.
        """
        return self.combat.check_damage_order_needed()


    def resolve_combat(self, seq_num: int):
        """
        Resolve combat damage.
        """
        return self.combat.resolve_combat(seq_num)


    def clear_combat(self):
        """
        Clear the current combat state.
        """
        self.combat.clear_combat()