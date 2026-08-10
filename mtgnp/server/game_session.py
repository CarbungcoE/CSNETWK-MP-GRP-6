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

        # IMPORTANT:
        # PriorityManager must exist BEFORE TurnEngine because
        # TurnEngine receives the PriorityManager instance.
        self.priority = PriorityManager(self.state)

        self.turn = TurnEngine(
            self.state,
            self.priority,
        )

        self.stack = StackManager(self.state)
        self.combat = CombatSystem(self.state)

    # ------------------------------------------------------------------
    # Game setup
    # ------------------------------------------------------------------

    def player_ready(
        self,
        player_id: str,
        deck_list: list,
    ) -> tuple[bool, str, dict]:
        """
        Process a PLAYER_READY request through the game lifecycle.
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

    # ------------------------------------------------------------------
    # Mulligan
    # ------------------------------------------------------------------

    def process_mulligan(
        self,
        player_id: str,
        keep: bool,
        cards_to_bottom: list,
    ):
        """
        Process a player's mulligan decision.

        Once both players have completed their mulligan,
        automatically start the first turn.
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
            self.start_game()

        return success, error

    def is_mulligan_complete(self) -> bool:
        """
        Check whether both players have completed the mulligan.
        """
        return self.lifecycle.is_mulligan_complete()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_visible_state(self, player_id: str):
        """
        Generate the state visible to a specific player.
        """
        return self.lifecycle.generate_visible_state(
            player_id
        )

    # ------------------------------------------------------------------
    # Turn / phase
    # ------------------------------------------------------------------

    def start_game(self) -> None:
        """
        Start the first turn after the mulligan phase.
        """
        self.state.consecutive_passes = 0
        self.turn.start_game()

    def begin_turn(self) -> None:
        """
        Begin a new turn.
        """
        self.state.consecutive_passes = 0
        self.turn.begin_turn()

    def advance_phase(self) -> str:
        """
        Advance to the next phase.

        Priority is cleared before the new phase receives
        priority. Only phases that support priority receive it.
        """
        self.state.consecutive_passes = 0
        self.state.priority_player = None

        new_phase = self.turn.advance_phase()

        if new_phase in {
            "MAIN_1",
            "COMBAT",
            "MAIN_2",
            "END",
        }:
            self.grant_active_player_priority()

        return new_phase

    # ------------------------------------------------------------------
    # Priority
    # ------------------------------------------------------------------

    def grant_priority(self, player_id: str) -> int:
        """
        Grant priority to a player.

        Returns the new priority sequence number.
        """
        return self.priority.grant_priority(
            player_id
        )

    def pass_priority(self) -> str | None:
        """
        Record a priority pass.

        With two players, the first pass transfers priority
        to the other player.

        When both players pass consecutively, the current
        phase advances.
        """
        if self.state.game_over:
            raise ValueError(
                "Cannot pass priority after game over"
            )

        if self.state.priority_player is None:
            raise ValueError(
                "Cannot pass priority when nobody has priority"
            )

        self.state.consecutive_passes += 1

        player_count = len(self.state.players)

        if player_count == 0:
            raise ValueError(
                "Cannot pass priority without players"
            )

        if self.state.consecutive_passes >= player_count:
            self.state.consecutive_passes = 0

            self.advance_phase()

            return self.state.priority_player

        return self.priority.pass_priority()

    def grant_active_player_priority(self) -> str:
        """
        Grant priority to the active player.
        """
        if self.state.active_player is None:
            raise ValueError(
                "Cannot grant priority without an active player"
            )

        self.state.consecutive_passes = 0

        self.priority.grant_priority(
            self.state.active_player
        )

        return self.state.active_player

    def has_priority(self, player_id: str) -> bool:
        """
        Check whether a player currently has priority.
        """
        return self.priority.has_priority(
            player_id
        )

    def get_priority_seq_num(self) -> int:
        """
        Return the authoritative priority sequence number.
        """
        return self.state.priority_seq_num

    def validate_priority_seq_num(
        self,
        seq_num: int,
    ) -> bool:
        """
        Validate a client's priority sequence number.
        """
        return self.priority.validate_seq_num(
            seq_num
        )

    # ------------------------------------------------------------------
    # Stack
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def declare_attackers(
        self,
        player_id: str,
        attackers: list,
    ):
        """
        Declare attackers for the active player.
        """
        return self.combat.declare_attackers(
            player_id,
            attackers,
        )

    def declare_blockers(
        self,
        player_id: str,
        blockers: list,
    ):
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