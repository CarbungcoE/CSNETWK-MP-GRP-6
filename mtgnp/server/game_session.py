from mtgnp.game.game_state import GameState
from mtgnp.game.lifecycle import GameLifecycle
from mtgnp.game.turn import TurnEngine
from mtgnp.game.priority import PriorityManager
from mtgnp.game.stack import StackManager
from mtgnp.game.combat import CombatSystem


class GameSession:
    """
    Represents one authoritative game session.

    GameSession owns the single GameState instance and
    provides access to the systems that operate on it.
    """

    def __init__(self):
        self.state = GameState()

        self.lifecycle = GameLifecycle(
            self.state
        )

        self.turn = TurnEngine(
            self.state
        )

        self.priority = PriorityManager(
            self.state
        )

        self.stack = StackManager(
            self.state
        )

        self.combat = CombatSystem(
            self.state
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def player_ready(
        self,
        player_id: str,
        deck_list: list,
    ):
        return self.lifecycle.process_player_ready(
            player_id,
            deck_list,
        )

    def start_setup(self):
        self.lifecycle.setup_game()

    def process_mulligan(
        self,
        player_id: str,
        keep: bool,
        cards_to_bottom: list,
    ):
        return self.lifecycle.process_mulligan(
            player_id,
            keep,
            cards_to_bottom,
        )

    def is_mulligan_complete(self) -> bool:
        return self.lifecycle.is_mulligan_complete()

    def get_visible_state(
        self,
        player_id: str,
    ):
        return self.lifecycle.generate_visible_state(
            player_id
        )

    # ------------------------------------------------------------------
    # Turn
    # ------------------------------------------------------------------

    def start_game(self):
        self.turn.start_game()

    def begin_turn(self):
        self.turn.begin_turn()

    def advance_phase(self):
        return self.turn.advance_phase()

    def requires_priority(self) -> bool:
        return self.turn.requires_priority()

    # ------------------------------------------------------------------
    # Priority
    # ------------------------------------------------------------------

    def grant_priority(
        self,
        player_id: str,
    ) -> int:
        return self.priority.grant_priority(
            player_id
        )

    def pass_priority(self):
        self.state.consecutive_passes += 1

        player_count = len(self.state.players)

        if self.state.consecutive_passes >= player_count:
            self.state.consecutive_passes = 0
            self.advance_phase()
            return self.state.priority_player

        return self.priority.pass_priority()

    def grant_active_player_priority(self):
        return self.priority.grant_active_player_priority()

    def has_priority(
        self,
        player_id: str,
    ) -> bool:
        return self.priority.has_priority(
            player_id
        )

    def get_priority_seq_num(self) -> int:
        return self.state.priority_seq_num

    def validate_priority_seq_num(
        self,
        seq_num: int,
    ) -> bool:
        return self.priority.validate_seq_num(
            seq_num
        )

    # ------------------------------------------------------------------
    # Mulligan sequence
    # ------------------------------------------------------------------

    def set_mulligan_seq(
        self,
        player_id: str,
        seq_num: int,
    ) -> None:
        self.state.mulligan_seq_nums[
            player_id
        ] = seq_num

    def get_mulligan_seq(
        self,
        player_id: str,
    ) -> int | None:
        return self.state.mulligan_seq_nums.get(
            player_id
        )

    def validate_mulligan_seq(
        self,
        player_id: str,
        seq_num: int,
    ) -> bool:
        expected = self.get_mulligan_seq(
            player_id
        )

        return (
            expected is not None
            and expected == seq_num
        )

    # ------------------------------------------------------------------
    # Stack
    # ------------------------------------------------------------------

    def push_stack(self, item: dict):
        self.stack.push(item)

    def pop_stack(self):
        return self.stack.pop()

    def peek_stack(self):
        return self.stack.peek()

    def resolve_stack(self):
        return self.stack.resolve_top()

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def declare_attackers(
        self,
        player_id: str,
        attackers: list,
    ):
        return self.combat.declare_attackers(
            player_id,
            attackers,
        )

    def declare_blockers(
        self,
        player_id: str,
        blockers: list,
    ):
        return self.combat.declare_blockers(
            player_id,
            blockers,
        )

    def check_damage_order_needed(self):
        return self.combat.check_damage_order_needed()

    def resolve_combat(
        self,
        seq_num: int,
    ):
        return self.combat.resolve_combat(
            seq_num
        )

    def clear_combat(self):
        self.combat.clear_combat()