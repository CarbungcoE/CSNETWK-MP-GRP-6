from mtgnp.game.game_state import GameState
from mtgnp.game.priority import PriorityManager


class TurnEngine:
    """
    Manages turn and phase progression for an active game.

    TurnEngine does not own game state. It operates on the authoritative
    GameState supplied by GameSession.
    """

    # Phases in their normal order during a turn.
    PHASES = [
        "UNTAP",
        "UPKEEP",
        "DRAW",
        "MAIN_1",
        "COMBAT",
        "MAIN_2",
        "END",
        "CLEANUP",
    ]

    def __init__(self, state: GameState):
        self.state = state
        self.priority = PriorityManager(state)

    def start_game(self) -> None:
        """
        Start the first turn after both players complete mulligans.
        """
        if self.state.phase != "MULLIGAN":
            raise ValueError(
                f"Cannot start game from phase {self.state.phase}"
            )

        if len(self.state.players) != 2:
            raise ValueError(
                "Cannot start game without exactly two players"
            )

        self.state.turn = 1

        if self.state.active_player is None:
            self.state.active_player = next(
                iter(self.state.players)
            )

        self.state.priority_player = None
        self.state.priority_seq_num = 0

        self._prepare_turn()

        # Automatic phases at the beginning of the first turn.
        self.state.phase = "UNTAP"
        self.state.phase = "UPKEEP"

        self.state.phase = "DRAW"

        # First player decision window.
        self.state.phase = "MAIN_1"

        self.grant_phase_priority()

    def begin_turn(self) -> None:
        """
        Begin a new turn for the current active player.
        """
        if self.state.game_over:
            raise ValueError(
                "Cannot begin a turn after game over"
            )

        if len(self.state.players) != 2:
            raise ValueError(
                "Cannot begin a turn without exactly two players"
            )

        self.state.turn += 1
        self.state.phase = "UNTAP"

        # Priority belongs to the turn/phase progression,
        # so clear any priority from the previous turn.
        self.state.priority_player = None

        self._prepare_turn()

        # Automatic phases at the beginning of the turn.
        self.state.phase = "UPKEEP"
        self.state.phase = "DRAW"

        # First decision window of the turn.
        self.state.phase = "MAIN_1"

        self.grant_phase_priority()

    def _prepare_turn(self) -> None:
        """
        Reset per-turn state for the active player.
        """
        if self.state.active_player is None:
            return

        player = self.state.players.get(
            self.state.active_player
        )

        if player is None:
            raise ValueError(
                "Active player is not registered in the game"
            )

        player.land_played_this_turn = False

    def _end_turn(self) -> None:
        """
        Finish the current turn and pass control to the other player.
        """
        player_ids = list(
            self.state.players.keys()
        )

        if len(player_ids) != 2:
            raise ValueError(
                "Cannot end turn without exactly two players"
            )

        if self.state.active_player not in player_ids:
            raise ValueError(
                "Active player is not registered in the game"
            )

        current_index = player_ids.index(
            self.state.active_player
        )

        next_index = (
            current_index + 1
        ) % len(player_ids)

        self.state.active_player = (
            player_ids[next_index]
        )

        self.begin_turn()
    def grant_phase_priority(self) -> str:
        """
        Grant priority to the active player for the current phase.
        """
        if self.state.phase not in {
            "MAIN_1",
            "COMBAT",
            "MAIN_2",
            "END",
        }:
            raise ValueError(
                f"Priority cannot be granted during {self.state.phase}"
            )

        return self.priority.grant_active_player_priority()