from typing import Any

from mtgnp.server.game_server import GameServer


class Dispatcher:
    """
    Routes incoming protocol messages to the appropriate game session
    and game system.

    Dispatcher handles protocol-level routing and validation.
    Game rules remain inside GameSession and its underlying systems.
    """

    # These messages use the PRIORITY sequence-number domain.
    PRIORITY_MESSAGES = {
        "PRIORITY_PASS",
        "CAST_SPELL",
        "ACTIVATE_ABILITY",
        "PLAY_LAND",
        "DECLARE_ATTACKERS",
        "DECLARE_BLOCKERS",
        "ASSIGN_DAMAGE_ORDER",
        "TRIGGER_ORDER_RESPONSE",
        "TRIGGER_CHOICE_RESPONSE",
    }

    def __init__(self, server: GameServer):
        self.server = server

    def dispatch(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        """
        Dispatch an incoming client message.
        """
        message_type = message.get("type")

        if not message_type:
            return self._error("MISSING_MESSAGE_TYPE")

        handler = {
            "PLAYER_READY": self.handle_player_ready,
            "MULLIGAN_CHOICE": self.handle_mulligan,
            "PRIORITY_PASS": self.handle_priority_pass,
            "DECLARE_ATTACKERS": self.handle_declare_attackers,
            "DECLARE_BLOCKERS": self.handle_declare_blockers,
            "ASSIGN_DAMAGE_ORDER": self.handle_assign_damage_order,
            "DISCARD": self.handle_discard,
            "CONCEDE": self.handle_concede,
            "CAST_SPELL": self.handle_cast_spell,
            "ACTIVATE_ABILITY": self.handle_activate_ability,
            "PLAY_LAND": self.handle_play_land,
            "TRIGGER_ORDER_RESPONSE": (
                self.handle_trigger_order_response
            ),
            "TRIGGER_CHOICE_RESPONSE": (
                self.handle_trigger_choice_response
            ),
        }.get(message_type)

        if handler is None:
            return self._error(
                "UNKNOWN_MESSAGE_TYPE",
                message_type=message_type,
            )

        # --------------------------------------------------------------
        # MULLIGAN
        # --------------------------------------------------------------
        #
        # Mulligan does NOT use the priority sequence.
        #
        # It echoes the authoritative GAME_STATE_UPDATE sequence.
        #
        if message_type == "MULLIGAN_CHOICE":
            error = self._validate_mulligan(
                player_id,
                message,
            )

            if error is not None:
                return error

        # --------------------------------------------------------------
        # PRIORITY ACTIONS
        # --------------------------------------------------------------
        elif message_type in self.PRIORITY_MESSAGES:
            error = self._validate_priority(
                player_id,
                message,
            )

            if error is not None:
                return error

        try:
            return handler(
                player_id,
                message,
            )

        except ValueError as exc:
            return self._error(
                "INVALID_REQUEST",
                detail=str(exc),
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_priority(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Validate the player's current priority and priority token.
        """
        session = self._get_player_session(player_id)

        if session is None:
            return self._error("NOT_IN_GAME")

        if not session.has_priority(player_id):
            return self._error(
                "NOT_PRIORITY_PLAYER"
            )

        seq_num = message.get("seq_num")

        if seq_num is None:
            return self._error(
                "MISSING_SEQUENCE_NUMBER"
            )

        try:
            seq_num = int(seq_num)
        except (TypeError, ValueError):
            return self._error(
                "INVALID_SEQUENCE_NUMBER"
            )

        if not session.validate_priority_seq_num(
            seq_num
        ):
            return self._error(
                "STALE_ACTION",
                expected_seq_num=session.get_priority_seq_num(),
                received_seq_num=seq_num,
            )

        return None

    def _validate_mulligan(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Validate a MULLIGAN_CHOICE sequence number.

        Mulligan uses the server GAME_STATE_UPDATE sequence.
        It does NOT use the priority sequence.
        """
        session = self._get_player_session(player_id)

        if session is None:
            return self._error("NOT_IN_GAME")

        if session.state.phase != "MULLIGAN":
            return self._error("WRONG_PHASE")

        seq_num = message.get("seq_num")

        if seq_num is None:
            return self._error(
                "MISSING_SEQUENCE_NUMBER"
            )

        try:
            seq_num = int(seq_num)
        except (TypeError, ValueError):
            return self._error(
                "INVALID_SEQUENCE_NUMBER"
            )

        expected = session.state.server_seq_num

        if seq_num != expected:
            return self._error(
                "STALE_ACTION",
                expected_seq_num=expected,
                received_seq_num=seq_num,
            )

        return None

    # ------------------------------------------------------------------
    # Game setup
    # ------------------------------------------------------------------

    def handle_player_ready(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        """
        Process PLAYER_READY.
        """
        session_id = message.get("session_id")

        if not session_id:
            return self._error(
                "MISSING_SESSION_ID"
            )

        try:
            session = self.server.get_or_create_session(
                session_id
            )
        except ValueError as exc:
            return self._error(str(exc))

        if player_id not in self.server.player_sessions:
            try:
                self.server.join_session(
                    session_id,
                    player_id,
                )
            except ValueError as exc:
                return self._error(str(exc))

        elif (
            self.server.player_sessions[player_id]
            != session_id
        ):
            return self._error(
                "PLAYER_ALREADY_IN_OTHER_GAME"
            )

        deck_list = message.get("deck_list")

        if deck_list is None:
            return self._error(
                "MISSING_DECK_LIST"
            )

        success, error, lobby_state = (
            session.player_ready(
                player_id,
                deck_list,
            )
        )

        if not success:
            return self._error(error)

        return {
            "type": "GAME_STATE_UPDATE",
            "state": lobby_state,
        }

    def handle_mulligan(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        """
        Process MULLIGAN_CHOICE.
        """

        session = self._get_player_session(player_id)

        if session is None:
            return self._error("NOT_IN_GAME")

        keep = message.get("keep")

        if keep is None:
            return self._error("MISSING_MULLIGAN_CHOICE")

        cards_to_bottom = message.get(
            "cards_to_bottom",
            [],
        )

        success, error = session.process_mulligan(
            player_id,
            keep,
            cards_to_bottom,
        )

        if not success:
            return self._error(error)

        return {
            "type": "MULLIGAN_RESULT",
            "player_id": player_id,
            "kept": keep,
        }

    # ------------------------------------------------------------------
    # Priority
    # ------------------------------------------------------------------

    def handle_priority_pass(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        """
        Process PRIORITY_PASS.
        """
        session = self._get_player_session(player_id)

        if session is None:
            return self._error(
                "NOT_IN_GAME"
            )

        next_player = session.pass_priority()

        return {
            "type": "PRIORITY_GRANT",
            "priority_player": next_player,
            "seq_num": session.get_priority_seq_num(),
        }

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def handle_declare_attackers(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        """
        Process DECLARE_ATTACKERS.
        """
        session = self._get_player_session(player_id)

        if session is None:
            return self._error(
                "NOT_IN_GAME"
            )

        attackers = message.get(
            "attackers",
            [],
        )

        error = session.declare_attackers(
            player_id,
            attackers,
        )

        if error:
            return self._error(error)

        return {
            "type": "ATTACKERS_DECLARED",
            "attackers": attackers,
        }

    def handle_declare_blockers(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        """
        Process DECLARE_BLOCKERS.
        """
        session = self._get_player_session(player_id)

        if session is None:
            return self._error(
                "NOT_IN_GAME"
            )

        blockers = message.get(
            "blockers",
            [],
        )

        error = session.declare_blockers(
            player_id,
            blockers,
        )

        if error:
            return self._error(error)

        return {
            "type": "BLOCKERS_DECLARED",
            "blockers": blockers,
        }

    def handle_assign_damage_order(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        """
        Process ASSIGN_DAMAGE_ORDER.
        """
        session = self._get_player_session(player_id)

        if session is None:
            return self._error(
                "NOT_IN_GAME"
            )

        damage_order = message.get(
            "damage_order"
        )

        if damage_order is None:
            return self._error(
                "MISSING_DAMAGE_ORDER"
            )

        return self._error(
            "NOT_IMPLEMENTED",
            detail=(
                "Damage ordering is not implemented yet."
            ),
        )

    # ------------------------------------------------------------------
    # Other game actions
    # ------------------------------------------------------------------

    def handle_discard(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        return self._error(
            "NOT_IMPLEMENTED",
            detail="Discard handling is not implemented yet.",
        )

    def handle_concede(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        session = self._get_player_session(player_id)

        if session is None:
            return self._error(
                "NOT_IN_GAME"
            )

        return self._error(
            "NOT_IMPLEMENTED",
            detail="Concede handling is not implemented yet.",
        )

    def handle_cast_spell(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        return self._error(
            "NOT_IMPLEMENTED",
            detail="Spell casting is not implemented yet.",
        )

    def handle_activate_ability(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        return self._error(
            "NOT_IMPLEMENTED",
            detail="Ability activation is not implemented yet.",
        )

    def handle_play_land(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        return self._error(
            "NOT_IMPLEMENTED",
            detail="Land playing is not implemented yet.",
        )

    def handle_trigger_order_response(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        return self._error(
            "NOT_IMPLEMENTED",
            detail="Trigger ordering is not implemented yet.",
        )

    def handle_trigger_choice_response(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        return self._error(
            "NOT_IMPLEMENTED",
            detail="Trigger choice handling is not implemented yet.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_player_session(
        self,
        player_id: str,
    ):
        """
        Return the GameSession associated with a player.
        """
        return self.server.get_player_session(
            player_id
        )

    @staticmethod
    def _error(
        code: str,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Create a standard error response.
        """
        return {
            "type": "ERROR",
            "error": code,
            **extra,
        }