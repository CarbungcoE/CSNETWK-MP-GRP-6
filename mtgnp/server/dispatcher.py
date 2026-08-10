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
            return self._error("UNKNOWN_TYPE")

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
                "UNKNOWN_TYPE",
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
                return self._finalize_error(error, message)

        # --------------------------------------------------------------
        # PRIORITY ACTIONS
        # --------------------------------------------------------------
        elif message_type == "TRIGGER_ORDER_RESPONSE":
            error = self._validate_trigger_order_response(player_id, message)
            if error is not None:
                return self._finalize_error(error, message)
        elif message_type == "TRIGGER_CHOICE_RESPONSE":
            error = self._validate_trigger_choice_response(player_id, message)
            if error is not None:
                return self._finalize_error(error, message)
        elif message_type == "DISCARD":
            error = self._validate_discard(player_id, message)
            if error is not None:
                return self._finalize_error(error, message)
        elif message_type in {"DECLARE_ATTACKERS", "DECLARE_BLOCKERS", "ASSIGN_DAMAGE_ORDER"}:
            error = self._validate_phase_action(player_id, message)
            if error is not None:
                return self._finalize_error(error, message)
        elif message_type in self.PRIORITY_MESSAGES:
            error = self._validate_priority(
                player_id,
                message,
            )

            if error is not None:
                return self._finalize_error(error, message)

        try:
            result = handler(player_id, message)
        except ValueError as exc:
            allowed = {
                "ILLEGAL_DECK", "UNKNOWN_TYPE", "STALE_ACTION",
                "NOT_YOUR_PRIORITY", "ILLEGAL_ACTION", "ILLEGAL_TARGET",
                "TRIGGER_ORDER_INVALID", "TRIGGER_CHOICE_INVALID",
                "INSUFFICIENT_MANA", "WRONG_PHASE", "DUPLICATE_ID",
                "DECK_EMPTY", "LIFE_ZERO", "CONCEDE", "DISCONNECT"
            }
            result = self._error(str(exc) if str(exc) in allowed else "ILLEGAL_ACTION", detail=str(exc))
        if isinstance(result, dict) and result.get("type") == "ERROR":
            return self._finalize_error(result, message)
        return result

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_priority(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:

        session = self._get_player_session(
            player_id
        )

        if session is None:
            return self._error(
                "ILLEGAL_ACTION"
            )

        if not session.has_priority(
            player_id
        ):
            return self._error(
                "NOT_YOUR_PRIORITY"
            )

        seq_num = message.get(
            "seq_num"
        )

        if seq_num is None:
            return self._error(
                "ILLEGAL_ACTION"
            )

        try:
            seq_num = int(seq_num)
        except (TypeError, ValueError):
            return self._error(
                "ILLEGAL_ACTION"
            )

        if not session.validate_priority_seq_num(
            seq_num
        ):
            return self._error(
                "STALE_ACTION",
                expected_seq_num=(
                    session.get_priority_seq_num()
                ),
                received_seq_num=seq_num,
            )

        return None

    
    def _validate_trigger_order_response(self, player_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        expected=session.state.pending_trigger_order_seq.get(player_id)
        if expected is None or message.get("seq_num") != expected:
            return self._error("STALE_ACTION", expected_seq_num=expected, received_seq_num=message.get("seq_num"))
        return None

    def _validate_trigger_choice_response(self, player_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        expected=session.state.pending_trigger_choice_seq.get(player_id)
        if expected is None or message.get("seq_num") != expected:
            return self._error("STALE_ACTION", expected_seq_num=expected, received_seq_num=message.get("seq_num"))
        return None

    def _validate_discard(self, player_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        expected=session.state.pending_discard_seq.get(player_id)
        if expected is None: return self._error("WRONG_PHASE")
        seq=message.get("seq_num")
        if seq is None: return self._error("ILLEGAL_ACTION")
        try: seq=int(seq)
        except (TypeError,ValueError): return self._error("ILLEGAL_ACTION")
        if seq != expected: return self._error("STALE_ACTION", expected_seq_num=expected, received_seq_num=seq)
        return None

    def _validate_phase_action(self, player_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        expected=session.state.phase_action_seq
        seq=message.get("seq_num")
        if seq is None: return self._error("ILLEGAL_ACTION")
        try: seq=int(seq)
        except (TypeError,ValueError): return self._error("ILLEGAL_ACTION")
        if seq != expected:
            return self._error("STALE_ACTION", expected_seq_num=expected, received_seq_num=seq)
        if message.get("type")=="DECLARE_ATTACKERS" and session.state.phase!="DECLARE_ATTACKERS": return self._error("WRONG_PHASE")
        if message.get("type")=="DECLARE_BLOCKERS" and session.state.phase!="DECLARE_BLOCKERS": return self._error("WRONG_PHASE")
        if message.get("type")=="ASSIGN_DAMAGE_ORDER" and session.state.phase!="ASSIGN_DAMAGE_ORDER": return self._error("WRONG_PHASE")
        return None

    def _validate_mulligan(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Validate a MULLIGAN_CHOICE sequence number.

        Mulligan uses the sequence number from the
        MULLIGAN GAME_STATE_UPDATE sent to the player.
        It does NOT use the priority sequence.
        """
        session = self._get_player_session(player_id)

        if session is None:
            return self._error("ILLEGAL_ACTION")

        if session.state.phase != "MULLIGAN":
            return self._error("WRONG_PHASE")

        seq_num = message.get("seq_num")

        if seq_num is None:
            return self._error(
                "ILLEGAL_ACTION"
            )

        try:
            seq_num = int(seq_num)
        except (TypeError, ValueError):
            return self._error(
                "ILLEGAL_ACTION"
            )

        expected = session.get_mulligan_seq(
            player_id
        )

        if expected is None:
            return self._error(
                "STALE_ACTION"
            )

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
                "ILLEGAL_ACTION"
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

        session = self._get_player_session(
            player_id
        )

        if session is None:
            return self._error(
                "ILLEGAL_ACTION"
            )

        seq_num = message.get(
            "seq_num"
        )

        if seq_num is None:
            return self._error(
                "ILLEGAL_ACTION"
            )

        try:
            seq_num = int(seq_num)
        except (TypeError, ValueError):
            return self._error(
                "ILLEGAL_ACTION"
            )

        # MULLIGAN_CHOICE echoes the GAME_STATE_UPDATE
        # that opened the current mulligan window.
        if not session.validate_mulligan_seq(
            player_id,
            seq_num,
        ):
            return self._error(
                "STALE_ACTION",
                expected_seq_num=(
                    session.get_mulligan_seq(
                        player_id
                    )
                ),
                received_seq_num=seq_num,
            )

        keep = message.get(
            "keep"
        )

        if keep is None:
            return self._error(
                "MISSING_MULLIGAN_CHOICE"
            )

        cards_to_bottom = message.get(
            "cards_to_bottom",
            [],
        )

        success, error = (
            session.process_mulligan(
                player_id,
                keep,
                cards_to_bottom,
            )
        )

        if not success:
            return self._error(
                error
            )

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
                "ILLEGAL_ACTION"
            )

        result = session.pass_priority()

        if result.get("advanced"):
            return {
                "type": "PRIORITY_PHASE_ADVANCED",
                "transitions": result.get("transitions", []),
                "priority_player": result.get("priority_player"),
                "priority_seq_num": result.get("priority_seq_num"),
                "phase": result.get("phase"),
                "turn": result.get("turn"),
                "active_player": result.get("active_player"),
            }
<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108

        if result.get("stack_resolved"):
            return {
                "type": "STACK_PRIORITY_RESOLVED",
                "stack_resolved": True,
                "resolved": result.get("resolved", {}),
                "priority_player": result.get("priority_player"),
                "priority_seq_num": result.get("priority_seq_num"),
                "phase": result.get("phase"),
                "turn": result.get("turn"),
                "active_player": result.get("active_player"),
            }
<<<<<<< HEAD
=======
=======
>>>>>>> 979dab4927d958bbfeba6ba88cf8fd8de7fcae04
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108

        return {
            "type": "PRIORITY_GRANT",
            "priority_player": result.get("priority_player"),
            "seq_num": result.get("priority_seq_num"),
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
                "ILLEGAL_ACTION"
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
                "ILLEGAL_ACTION"
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

    def handle_assign_damage_order(self, player_id: str, message: dict[str, Any]) -> Any:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        attacker_id=message.get("attacker_id")
        blocker_order=message.get("blocker_order")
        if not attacker_id or not isinstance(blocker_order,list): return self._error("ILLEGAL_ACTION")
        try: result=session.assign_damage_order(player_id, attacker_id, blocker_order)
        except ValueError as exc: return self._error(str(exc))
        return {"type":"DAMAGE_ORDER_ASSIGNED", **result}

    # ------------------------------------------------------------------
    # Other game actions
    # ------------------------------------------------------------------

    def handle_discard(self, player_id: str, message: dict[str, Any]) -> Any:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        try: result=session.discard(player_id, message.get("card_ids", []))
        except ValueError as exc: return self._error(str(exc))
        return {"type":"DISCARD_RESULT", **result}

    def handle_concede(self, player_id: str, message: dict[str, Any]) -> Any:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        try: result=session.concede(player_id)
        except ValueError as exc: return self._error(str(exc))
        return {"type":"GAME_OVER", **result}

    def handle_cast_spell(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        session = self._get_player_session(player_id)
        if session is None:
<<<<<<< HEAD
            return self._error("ILLEGAL_ACTION")
=======
            return self._error("NOT_IN_GAME")

        card_id = message.get("card_id")
        if not card_id:
            return self._error("MISSING_CARD_ID")

        targets = message.get("targets", [])
        mana_payment = message.get("mana_payment", {})

        try:
            result = session.cast_spell(
                player_id,
                card_id,
                targets,
                mana_payment,
            )
        except ValueError as exc:
            return self._error(str(exc))

        return {
            "type": "SPELL_CAST",
            **result,
        }
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108

        card_id = message.get("card_id")
        if not card_id:
            return self._error("ILLEGAL_ACTION")

        targets = message.get("targets", [])
        mana_payment = message.get("mana_payment", {})

        try:
            result = session.cast_spell(
                player_id,
                card_id,
                targets,
                mana_payment,
            )
        except ValueError as exc:
            return self._error(str(exc))

        return {
            "type": "SPELL_CAST",
            **result,
        }

    def handle_activate_ability(self, player_id: str, message: dict[str, Any]) -> Any:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        source_id=message.get("source_id"); ability_index=message.get("ability_index")
        if source_id is None or ability_index is None: return self._error("ILLEGAL_ACTION")
        try:
            result=session.activate_ability(player_id, source_id, int(ability_index), message.get("targets", []), message.get("cost_payment", {}))
        except ValueError as exc: return self._error(str(exc))
        return result

    def handle_play_land(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> Any:
        session = self._get_player_session(player_id)
<<<<<<< HEAD
=======

        if session is None:
            return self._error(
                "NOT_IN_GAME"
            )

        card_id = message.get("card_id")

        if not card_id:
            return self._error(
                "MISSING_CARD_ID"
            )

        try:
            result = session.play_land(
                player_id,
                card_id,
            )
        except ValueError as exc:
            return self._error(
                str(exc),
            )

        return {
            "type": "LAND_PLAYED",
            "player_id": result["player_id"],
            "card_id": result["card_id"],
        }
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108

        if session is None:
            return self._error(
                "ILLEGAL_ACTION"
            )

        card_id = message.get("card_id")

        if not card_id:
            return self._error(
                "ILLEGAL_ACTION"
            )

        try:
            result = session.play_land(
                player_id,
                card_id,
            )
        except ValueError as exc:
            return self._error(
                str(exc),
            )

        return {
            "type": "LAND_PLAYED",
            "player_id": result["player_id"],
            "card_id": result["card_id"],
        }

    def handle_trigger_order_response(self, player_id: str, message: dict[str, Any]) -> Any:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        pending=session.state.pending_trigger_orders.get(player_id)
        if pending is None: return self._error("TRIGGER_ORDER_INVALID")
        ids=message.get("ordered_trigger_ids")
        if not isinstance(ids,list) or ids != pending["trigger_ids"] and set(ids)!=set(pending["trigger_ids"]): return self._error("TRIGGER_ORDER_INVALID")
        session.state.pending_trigger_orders.pop(player_id,None)
        session.state.pending_trigger_order_seq.pop(player_id,None)
        items=[]
        for tid in reversed(ids):
            item=pending["items"][tid]; session.push_stack(item); items.append(item)
        return {"type":"TRIGGER_ORDER_ACCEPTED","trigger_ids":ids,"items":items}

    def handle_trigger_choice_response(self, player_id: str, message: dict[str, Any]) -> Any:
        session=self._get_player_session(player_id)
        if session is None: return self._error("ILLEGAL_ACTION")
        pending=session.state.pending_trigger_choices.get(player_id)
        if pending is None or message.get("trigger_id") != pending.get("trigger_id"): return self._error("TRIGGER_CHOICE_INVALID")
        if pending.get("requires_target") and message.get("accept") and message.get("chosen_target") not in pending.get("legal_targets",[]): return self._error("ILLEGAL_TARGET")
        session.state.pending_trigger_choices.pop(player_id,None)
        session.state.pending_trigger_choice_seq.pop(player_id,None)
        item=pending["item"]
        if message.get("accept"):
            item["targets"]=[message.get("chosen_target")] if message.get("chosen_target") else []
            session.push_stack(item)
            return {"type":"TRIGGER_CHOICE_ACCEPTED","trigger_id":message.get("trigger_id"),"accepted":True,"item":item}
        return {"type":"TRIGGER_CHOICE_ACCEPTED","trigger_id":message.get("trigger_id"),"accepted":False,"item":None}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _finalize_error(error: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
        if error.get("type") != "ERROR": return error
        result=dict(error)
        result.setdefault("seq_num", message.get("seq_num",0))
        result.setdefault("rejected_action", dict(message))
        result.pop("error",None)
        return result

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
            "code": code,
            "message": extra.pop("message", code),
            **extra,
        }