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
        "FIRST_STRIKE_DAMAGE",
        "COMBAT_DAMAGE",
        "END_OF_COMBAT",
        "POSTCOMBAT_MAIN",
        "END_STEP",
    }

    def __init__(self, state: GameState):
        self.state = state

    def start_game(self) -> list[dict]:
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
        previous_phase = self.state.phase
        self.state.phase = "UNTAP"
        self.state.priority_player = None
        self.state.priority_seq_num = 0
        self.state.consecutive_passes = 0

        if self.state.active_player is None:
            self.state.active_player = next(
                iter(self.state.players)
            )

        self._prepare_turn()
        self._untap_active_player()

        return [{"from_phase": previous_phase, "to_phase": "UNTAP"}]

    def begin_turn(self) -> list[dict]:
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

        previous_phase = self.state.phase
        self.state.turn += 1
        self.state.phase = "UNTAP"
        self.state.priority_player = None
        self.state.priority_seq_num = 0
        self.state.consecutive_passes = 0
        self.state.phase_decision_complete = False

        self._prepare_turn()
        self._untap_active_player()

        return [{"from_phase": previous_phase, "to_phase": "UNTAP"}]

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
            return self.state.phase

        self.state.phase = self.PHASES[current_index + 1]
        self.state.priority_player = None
        self.state.consecutive_passes = 0
        self.state.phase_decision_complete = False

        self._on_phase_enter(self.state.phase)
        return self.state.phase

    def requires_priority(self) -> bool:
        return self.state.phase in self.PRIORITY_PHASES


    def _on_phase_enter(self, phase: str) -> None:
        """Apply automatic rules that occur when entering a phase."""
        if phase == "UNTAP":
            self._prepare_turn()
            self._untap_active_player()
        elif phase == "DRAW":
            self._draw_step()
        elif phase == "CLEANUP":
            self._cleanup_step()
        elif phase in {"BEGIN_COMBAT", "DECLARE_ATTACKERS"}:
            self.state.phase_decision_complete = False

    def _untap_active_player(self) -> None:
        """Untap all permanents controlled by the active player."""
        if self.state.active_player is None:
            return
        player = self.state.players.get(self.state.active_player)
        if player is None:
            raise ValueError("Active player is not registered")

        for permanent in player.battlefield:
            permanent["tapped"] = False
            if permanent.get("summoning_sickness"):
                permanent["summoning_sickness"] = False

    def _draw_step(self) -> None:
        """Perform the automatic draw, except on the first turn."""
        if self.state.active_player is None:
            raise ValueError("Active player is not registered")

        player = self.state.players.get(self.state.active_player)
        if player is None:
            raise ValueError("Active player is not registered")

        # MTGNP 1.0: the first player skips their first draw step.
        if self.state.turn == 1:
            return

        if not player.library:
            self.state.game_over = True
            self.state.winner = next(
                (pid for pid in self.state.players if pid != self.state.active_player),
                None,
            )
            self.state.game_over_reason = "DECK_EMPTY"
            self.state.priority_player = None
            return

        player.hand.append(player.library.pop())

    def _cleanup_step(self) -> None:
        """Apply automatic cleanup effects that do not require player input."""
        if self.state.active_player is None:
            return
        player = self.state.players.get(self.state.active_player)
        if player is None:
            raise ValueError("Active player is not registered")

        # Remove damage, temporary effects, and per-turn prevention flags.
        for permanent in player.battlefield:
            if "damage" in permanent: permanent["damage"] = 0
            if permanent.get("temp_power"): permanent.pop("temp_power", None)
            if permanent.get("temp_toughness"): permanent.pop("temp_toughness", None)
            permanent.pop("protection_until_turn", None)
        for p in self.state.players.values():
            p.damage_prevention = 0
            p.life_gain_prevented = False
            p.damage_prevented = False
            for c in p.battlefield:
                if c.get("attacking"): c.pop("attacking", None)

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