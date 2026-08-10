from mtgnp.game.game_state import GameState


class TurnEngine:
    """
    Manages turn and phase progression.

    TurnEngine does not own GameState. It operates on the
    authoritative GameState supplied by GameSession.
    """

    PHASES = [
        "UNTAP",
        "UPKEEP",
        "DRAW",
        "PRECOMBAT_MAIN",
        "BEGIN_COMBAT",
        "DECLARE_ATTACKERS",
        "DECLARE_BLOCKERS",
        "ASSIGN_DAMAGE_ORDER",
        "FIRST_STRIKE_DAMAGE",
        "COMBAT_DAMAGE",
        "END_OF_COMBAT",
        "POSTCOMBAT_MAIN",
        "END_STEP",
        "CLEANUP",
    ]

    PRIORITY_PHASES = {
        "UPKEEP",
        "DRAW",
        "PRECOMBAT_MAIN",
        "BEGIN_COMBAT",
        "DECLARE_ATTACKERS",
        "DECLARE_BLOCKERS",
        "ASSIGN_DAMAGE_ORDER",
        "FIRST_STRIKE_DAMAGE",
        "COMBAT_DAMAGE",
        "END_OF_COMBAT",
        "POSTCOMBAT_MAIN",
        "END_STEP",
    }

    def __init__(self, state: GameState):
        self.state = state

    def start_game(self) -> None:
        """
        Transition from MULLIGAN into the first turn.

        The first turn starts at UNTAP. UNTAP does not receive
        priority; the server must subsequently advance to UPKEEP.
        """

        if self.state.phase != "MULLIGAN":
            raise ValueError(
                f"Cannot start game from phase {self.state.phase}"
            )

        if len(self.state.players) < 2:
            raise ValueError(
                "Cannot start game without two players"
            )

        self.state.turn = 1
        self.state.phase = "UNTAP"
        self.state.priority_player = None
        self.state.priority_seq_num = 0

        if self.state.active_player is None:
            self.state.active_player = next(
                iter(self.state.players)
            )

        self._prepare_turn()

    def begin_turn(self) -> None:
        """
        Begin a new turn.
        """

        if self.state.game_over:
            raise ValueError(
                "Cannot begin a turn after game over"
            )

        if not self.state.players:
            raise ValueError(
                "Cannot begin a turn without players"
            )

        self.state.turn += 1
        self.state.phase = "UNTAP"
        self.state.priority_player = None

        self._prepare_turn()

    def advance_phase(self) -> str:
        """
        Advance to the next phase/step.

        Returns the resulting phase.
        """

        if self.state.game_over:
            raise ValueError(
                "Cannot advance phase after game over"
            )

        if self.state.phase not in self.PHASES:
            raise ValueError(
                f"Cannot advance from phase {self.state.phase}"
            )

        current_index = self.PHASES.index(
            self.state.phase
        )

        if current_index == len(self.PHASES) - 1:
            self._end_turn()
        else:
            self.state.phase = self.PHASES[
                current_index + 1
            ]

        self.state.priority_player = None

        return self.state.phase

    def requires_priority(self) -> bool:
        return self.state.phase in self.PRIORITY_PHASES

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
                "Active player is not registered"
            )

        player.land_played_this_turn = False

    def _end_turn(self) -> None:
        """
        Finish the current turn and switch active player.
        """

        player_ids = list(
            self.state.players.keys()
        )

        if not player_ids:
            raise ValueError(
                "Cannot end turn without players"
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