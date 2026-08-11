import socket
import select
import time

from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger
from mtgnp.common.pdu import (
    build_pong,
    build_error,
    build_phase_transition,
    validate_pdu,
    PDUValidationError,
)

from mtgnp.server.game_server import GameServer
from mtgnp.server.dispatcher import Dispatcher


class MTGNPServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4444,
        verbose: bool = False,
    ):
        self.host = host
        self.port = port
        self.verbose = verbose

        self.logger = VerboseLogger(
            enabled=verbose,
            label="SERVER",
        )

        # Transport/server sequence number.
        #
        # This is ONLY for numbering server -> client PDUs.
        # It must NOT be used as the game's authoritative
        # action sequence number.
        self.server_seq_num = 1
        self.priority_time_limit_ms = 60000
        self.priority_deadlines: dict[str,float] = {}
        self.disconnect_deadlines: dict[str,tuple[str,float]] = {}

        self.running = False
        self.server_sock = None

        # {
        #     socket: {
        #         "addr": (...),
        #         "player_id": None | "player_1" | "player_2",
        #     }
        # }
        self.clients = {}

        self.game_server = GameServer()
        self.dispatcher = Dispatcher(self.game_server)

    # ================================================================
    # SERVER LIFECYCLE
    # ================================================================

    def start(self):
        self.running = True

        self.server_sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        self.server_sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        self.server_sock.bind(
            (self.host, self.port)
        )

        self.server_sock.listen(2)

        print(
            f"Server started on {self.host}:{self.port}. "
            f"Verbose={self.verbose}"
        )

        try:
            while self.running:
                sockets_to_watch = (
                    [self.server_sock]
                    + list(self.clients.keys())
                )

                readable, _, _ = select.select(
                    sockets_to_watch,
                    [],
                    [],
                    1,
                )
                self._check_timeouts()
                for sock in readable:
                    if sock is self.server_sock:
                        self._accept_client()
                    else:
                        self._handle_client_data(sock)

        except KeyboardInterrupt:
            print("\nShutdown signal received.")

        finally:
            self.stop()

    # ================================================================
    # CLIENT CONNECTION
    # ================================================================

    def _accept_client(self):
        """
        Accept a new TCP connection.

        Player identity is established later by PLAYER_READY.
        """
        conn, addr = self.server_sock.accept()
        if len(self.clients) >= 2:
            try:
                conn.close()
            finally:
                print(f"Rejected extra client connection from {addr} (game full).")
            return

        self.clients[conn] = {
            "addr": addr,
            "player_id": None,
            "last_server_seq": 0,
        }

        print(
            f"Client connected from {addr}."
        )

    # ================================================================
    # CLIENT DATA
    # ================================================================

    def _handle_client_data(self, conn):
        try:
            pdu = recv_pdu(conn)

            if not pdu:
                self._handle_disconnect(conn)
                return

            client_info = self.clients.get(conn)

            if client_info is None:
                self._handle_disconnect(conn)
                return

            self.logger.log_pdu(
                "C->S",
                pdu,
            )

            try:
                validate_pdu(pdu)
            except PDUValidationError as exc:
                self._send_error(conn, 0, "ILLEGAL_ACTION", str(exc), pdu)
                return

            pdu_type = pdu.get("type")

            # --------------------------------------------------------
            # HEARTBEAT
            # --------------------------------------------------------

            if pdu_type == "PING":
                pong = build_pong(
                    pdu.get("seq_num", 0),
                    pdu.get("timestamp", 0),
                )

                send_pdu(
                    conn,
                    pong,
                )

                self.logger.log_pdu(
                    "S->C",
                    pong,
                )

                return

            # --------------------------------------------------------
            # PLAYER_READY
            # --------------------------------------------------------

            # PLAYER_READY establishes the protocol-level identity.
            if pdu_type == "PLAYER_READY":
                player_id = pdu.get("player_id")

                if player_id and any(info.get("player_id") == player_id and c is not conn for c,info in self.clients.items()):
                    self._send_error(conn, pdu.get("seq_num",0), "DUPLICATE_ID", "Player ID is already claimed by another connection.", pdu)
                    return

                if not player_id:
                    self._send_error(conn,pdu.get("seq_num",0),"ILLEGAL_ACTION","PLAYER_READY requires player_id.",pdu)
                    return

                reconnect=self.disconnect_deadlines.get(player_id)
                if reconnect is not None:
                    session_id,_=reconnect
                    session=self.game_server.sessions.get(session_id)
                    if session is not None and not session.state.game_over:
                        client_info["player_id"]=player_id
                        self.disconnect_deadlines.pop(player_id,None)
                        self._broadcast_game_state(session)
                        if session.state.priority_player==player_id:
                            self._send_response(conn,{"type":"PRIORITY_GRANT","player_id":player_id,"time_limit_ms":self.priority_time_limit_ms})
                        return

                response = self.dispatcher.dispatch(
                    player_id,
                    pdu,
                )

                if response is None:
                    return

                # Establish socket -> player identity.
                client_info["player_id"] = player_id

                # ------------------------------------------------------------
                # If both players are now ready, the dispatcher response
                # represents the transition into MULLIGAN.
                #
                # The MULLIGAN GAME_STATE_UPDATE must be sent to BOTH players
                # using the SAME server sequence number.
                # ------------------------------------------------------------

                session = self.game_server.get_player_session(
                    player_id
                )

                if session is not None and session.state.phase == "MULLIGAN":
                    self._broadcast_game_state(session)
                    return

                # Normal PLAYER_READY response while still in LOBBY.
                self._send_response(
                    conn,
                    response,
                )

                return



            # --------------------------------------------------------
            # ALL OTHER GAME ACTIONS
            # --------------------------------------------------------

            player_id = client_info.get("player_id")

            if not player_id:
                self._send_error(
                    conn,
                    0,
                    "PLAYER_NOT_IDENTIFIED",
                    "Send PLAYER_READY before other game actions.",
                )
                return

            response = self.dispatcher.dispatch(
                player_id,
                pdu,
            )

            if response is not None:
                if response.get("type") == "PRIORITY_GRANT":
                    session = self.game_server.get_player_session(player_id)
                    self._send_response(conn, response)
                    if session is not None:
                        self._broadcast_game_state(session)
                    return
                if response.get("type") == "ERROR":
                    session=self.game_server.get_player_session(player_id)
                    self._send_response(conn,response)
                    if session is not None and session.state.priority_player==player_id and pdu_type in Dispatcher.PRIORITY_MESSAGES:
                        self._send_response(conn,{"type":"PRIORITY_GRANT","player_id":player_id,"time_limit_ms":self.priority_time_limit_ms,"_reissue":True})
                    return
                if response.get("type") == "SPELL_CAST":
                    session = self.game_server.get_player_session(player_id)
                    if session is not None:
                        from mtgnp.common.pdu import build_stack_push
                        self.broadcast(
                            build_stack_push(
                                0,
                                response["stack_item_id"],
                                response["item_type"],
                                response["source"],
                                response["targets"],
                                response["controller"],
                            )
                        )
                        self._send_response(
                            conn,
                            {
                                "type": "PRIORITY_GRANT",
                                "player_id": player_id,
                                "time_limit_ms": self.priority_time_limit_ms,
                            },
                        )
                        self._broadcast_game_state(session)

                elif response.get("type") == "LAND_PLAYED":
                    session = self.game_server.get_player_session(
                        player_id
                    )

                    if session is not None:
                        # PLAY_LAND bypasses the stack. The Active Player
                        # keeps priority, so broadcast the updated state
                        # and then issue a fresh priority token.
                        session.grant_active_player_priority()
                        self._send_response(
                            conn,
                            {
                                "type": "PRIORITY_GRANT",
                                "player_id": player_id,
                                "time_limit_ms": self.priority_time_limit_ms,
                            },
                        )
                        self._broadcast_game_state(session)

                elif response.get("type") == "ATTACKERS_DECLARED":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        if not session.combat.atks:
                            session.state.phase_decision_complete=True
                            session.advance_phase()  # DECLARE_BLOCKERS
                            session.advance_phase()  # ASSIGN_DAMAGE_ORDER
                            session.advance_phase()  # FIRST_STRIKE_DAMAGE
                            session.advance_phase()  # COMBAT_DAMAGE
                            session.resolve_combat_damage(False)
                            session._check_state_based_actions()
                            session.clear_combat()
                            session.advance_phase()  # END_OF_COMBAT
                            self.broadcast(build_phase_transition(0, "DECLARE_ATTACKERS", "END_OF_COMBAT", session.state.active_player, session.state.turn))
                            self._broadcast_game_state(session)
                        else:
                            session.grant_active_player_priority()
                            self._send_response(conn,{"type":"PRIORITY_GRANT","player_id":player_id,"time_limit_ms":self.priority_time_limit_ms})
                            self._broadcast_game_state(session)
                elif response.get("type") == "BLOCKERS_DECLARED":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        needed=session.check_damage_order_needed()
                        if needed:
                            session.advance_phase()
                            self.broadcast(build_phase_transition(0,"DECLARE_BLOCKERS","ASSIGN_DAMAGE_ORDER",session.state.active_player,session.state.turn))
                            self._broadcast_game_state(session)
                        else:
                            session.grant_active_player_priority()
                            self._send_response(conn,{"type":"PRIORITY_GRANT","player_id":session.state.priority_player,"time_limit_ms":self.priority_time_limit_ms})
                            self._broadcast_game_state(session)
                elif response.get("type") == "DAMAGE_ORDER_ASSIGNED":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        if all(a in session.combat.atk_order for a in session.check_damage_order_needed()):
                            session.state.phase_decision_complete=True
                            session.grant_active_player_priority()
                            self._send_response(conn,{"type":"PRIORITY_GRANT","player_id":session.state.priority_player,"time_limit_ms":self.priority_time_limit_ms})
                            self._broadcast_game_state(session)
                elif response.get("type") == "ABILITY_ACTIVATED":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None and response.get("stack_item_id"):
                        from mtgnp.common.pdu import build_stack_push
                        self.broadcast(build_stack_push(0,response["stack_item_id"],response["item_type"],response["source"],response["targets"],response["controller"]))
                        self._send_response(conn,{"type":"PRIORITY_GRANT","player_id":player_id,"time_limit_ms":self.priority_time_limit_ms})
                        self._broadcast_game_state(session)
                elif response.get("type") == "DISCARD_RESULT":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        session.state.pending_discard_seq.pop(player_id,None)
                        # Cleanup completes automatically once all oversized hands are handled.
                        if not any(len(p.hand)>7 for p in session.state.players.values()):
                            session.advance_phase()
                            self._broadcast_game_state(session)

                elif response.get("type") == "GAME_OVER":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        from mtgnp.common.pdu import build_game_over
                        self.broadcast(build_game_over(0,response.get("winner_id"),response.get("loser_id"),response.get("reason")))
                        # Retain TCP connections; replace authoritative session.
                        sid=self.game_server.player_sessions.get(player_id)
                        if sid:
                            self.game_server.reset_session(sid)
                elif response.get("type") == "DISCARD_RESULT":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        self._broadcast_game_state(session)
                
                elif response.get("type") == "STACK_PRIORITY_RESOLVED":
                    session = self.game_server.get_player_session(player_id)
                    if session is not None:
                        from mtgnp.common.pdu import build_stack_resolve, build_game_over
                        resolved = response.get("resolved", {})
                        self.broadcast(
                            build_stack_resolve(
                                0,
                                resolved.get("stack_item_id"),
                                resolved.get("result", "FIZZLE"),
                                resolved.get("state_changes", []),
                            )
                        )
                        if self._emit_pending_trigger_requests(session): return

                        if session.state.game_over:
                            loser = next((pid for pid, p in session.state.players.items() if p.life <= 0), None)
                            winner = session.state.winner
                            self.broadcast(build_game_over(0,winner,loser,session.state.game_over_reason or "LIFE_ZERO"))
                            sid=self.game_server.player_sessions.get(player_id)
                            if sid: self.game_server.reset_session(sid)
                        else:
                            self._send_response(
                                conn,
                                {
                                    "type": "PRIORITY_GRANT",
                                    "player_id": response.get("priority_player") or response.get("player_id"),
                                    "time_limit_ms": self.priority_time_limit_ms,
                                },
                            )
                            self._broadcast_game_state(session)

                elif response.get("type") == "TRIGGER_ORDER_ACCEPTED":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        from mtgnp.common.pdu import build_stack_push
                        for item in response.get("items", []):
                            self.broadcast(build_stack_push(0,item["stack_item_id"],item["item_type"],item.get("source_id"),item.get("targets",[]),item.get("controller_id")))
                        if not self._emit_pending_trigger_requests(session) and not session.state.game_over:
                            session.grant_active_player_priority(); target=session.state.priority_player
                            conn2=next((c for c,i in self.clients.items() if i.get("player_id")==target),None)
                            if conn2 is not None: self._send_response(conn2,{"type":"PRIORITY_GRANT","player_id":target,"time_limit_ms":self.priority_time_limit_ms})
                        self._broadcast_game_state(session)

                elif response.get("type") == "TRIGGER_CHOICE_ACCEPTED":
                    session=self.game_server.get_player_session(player_id)
                    if session is not None:
                        item=response.get("item")
                        if item is not None:
                            from mtgnp.common.pdu import build_stack_push
                            self.broadcast(build_stack_push(0,item["stack_item_id"],item["item_type"],item["source_id"],item.get("targets",[]),item["controller_id"]))
                        if not self._emit_pending_trigger_requests(session) and not session.state.game_over:
                            session.grant_active_player_priority(); target=session.state.priority_player
                            conn2=next((c for c,i in self.clients.items() if i.get("player_id")==target),None)
                            if conn2 is not None: self._send_response(conn2,{"type":"PRIORITY_GRANT","player_id":target,"time_limit_ms":self.priority_time_limit_ms})
                        self._broadcast_game_state(session)

                elif response.get("type") == "PRIORITY_PHASE_ADVANCED":
                    session = self.game_server.get_player_session(
                        player_id
                    )

                    if session is not None:
                        # Broadcast each phase transition, including any
                        # automatic phases skipped without priority.
                        for transition in response.get("transitions", []):
                            self.broadcast(
                                build_phase_transition(
                                    0,
                                    transition["from_phase"],
                                    transition["to_phase"],
                                    session.state.active_player,
                                    session.state.turn,
                                )
                            )

                        # Broadcast automatic combat results before the next state snapshot.
                        from mtgnp.common.pdu import build_combat_damage_result, build_game_over
                        for result in response.get("combat_results", []):
                            self.broadcast(build_combat_damage_result(0, result.get("damage_events", []), result.get("life_totals", {}), result.get("creatures_died", [])))
                        if session.state.game_over:
                            loser=next((pid for pid,p in session.state.players.items() if p.life<=0),None)
                            self.broadcast(build_game_over(0,session.state.winner,loser,session.state.game_over_reason or "LIFE_ZERO"))
                            sid=self.game_server.player_sessions.get(player_id)
                            if sid: self.game_server.reset_session(sid)
                        else:
                            if session.state.priority_player is not None:
                                target=session.state.priority_player; target_conn=next((c for c,i in self.clients.items() if i.get("player_id")==target),None)
                                if target_conn is not None: self._send_response(target_conn,{"type":"PRIORITY_GRANT","player_id":target,"time_limit_ms":self.priority_time_limit_ms})
                            self._broadcast_game_state(session)
                else:
                    self._send_response(
                        conn,
                        response,
                    )

            # --------------------------------------------------------
            # MULLIGAN -> FIRST TURN
            # --------------------------------------------------------
            #
            # Dispatcher.handle_mulligan() records the player's choice
            # and returns MULLIGAN_RESULT.  It intentionally does not
            # own the socket-level broadcast/turn transition.
            #
            # Once BOTH players have kept their hands, start the first
            # turn and immediately run the non-priority opening phases
            # until the first priority window.
            #
            # TurnEngine.start_game() moves MULLIGAN -> UNTAP.  UNTAP
            # itself does not receive priority, so advance once more to
            # UPKEEP and grant priority to the active player.
            # --------------------------------------------------------
            if (
                pdu_type == "MULLIGAN_CHOICE"
                and response.get("type") == "MULLIGAN_RESULT"
            ):
                session = self.game_server.get_player_session(
                    player_id
                )

                if session is not None and session.is_mulligan_complete():
                    try:
                        transitions = session.start_game()

                        # Broadcast the authoritative transition into UNTAP.
                        for transition in transitions or []:
                            self.broadcast(
                                build_phase_transition(
                                    0,
                                    transition["from_phase"],
                                    transition["to_phase"],
                                    session.state.active_player,
                                    session.state.turn,
                                )
                            )

                        # UNTAP is automatic and receives no priority.
                        # Advance immediately to UPKEEP, then open priority.
                        if session.state.phase == "UNTAP":
                            from_phase = session.state.phase
                            to_phase = session.advance_phase()
                            self.broadcast(
                                build_phase_transition(
                                    0,
                                    from_phase,
                                    to_phase,
                                    session.state.active_player,
                                    session.state.turn,
                                )
                            )

                        if (
                            session.state.phase == "UPKEEP"
                            and session.state.priority_player is None
                            and not session.state.game_over
                        ):
                            session.grant_active_player_priority()

                        if session.state.priority_player is not None and not session.state.game_over:
                            target=session.state.priority_player; target_conn=next((c for c,i in self.clients.items() if i.get("player_id")==target),None)
                            if target_conn is not None: self._send_response(target_conn,{"type":"PRIORITY_GRANT","player_id":target,"time_limit_ms":self.priority_time_limit_ms})
                        self._broadcast_game_state(session)

                    except ValueError as exc:
                        self._send_error(
                            conn,
                            0,
                            "GAME_START_FAILED",
                            str(exc),
                        )
                elif session is not None:
                    # A mulligan rejection is a complete action by itself.
                    # The lifecycle has already dealt the replacement hand;
                    # publish that authoritative hand before asking the
                    # client for its next keep decision.
                    self._broadcast_game_state(session)

        except ValueError as ve:
            print(
                f"Framing/Value error: {ve}"
            )

            self._send_error(
                conn,
                0,
                "INVALID_JSON",
                str(ve),
            )

        except ConnectionResetError:
            self._handle_disconnect(conn)

        except ConnectionAbortedError:
            self._handle_disconnect(conn)

        except OSError:
            self._handle_disconnect(conn)

        except Exception as e:
            print(
                f"Unexpected error receiving data: {e}"
            )

            self._handle_disconnect(conn)

    def _broadcast_game_state(self, session):
        for conn,info in list(self.clients.items()):
            pid=info.get("player_id")
            if pid is None or self.game_server.get_player_session(pid) is not session: continue
            self._send_response(conn,{"type":"GAME_STATE_UPDATE","state":session.get_visible_state(pid)})

    # ================================================================
    # SERVER -> CLIENT
    # ================================================================

    def _next_server_seq(self):
        seq=self.server_seq_num; self.server_seq_num+=1; return seq

    def _send_response(self,conn,pdu):
        if pdu is None: return
        response=dict(pdu); typ=response.get("type")
        if typ=="GAME_STATE_UPDATE":
            pid=(self.clients.get(conn) or {}).get("player_id")
            response["seq_num"]=self._next_server_seq()
            session=self.game_server.get_player_session(pid) if pid else None
            if session is not None:
                if session.state.phase=="MULLIGAN":
                    player = session.state.players.get(pid)
                    if player is not None and not player.kept_hand:
                        session.set_mulligan_seq(pid,response["seq_num"])
                if session.state.phase=="CLEANUP" and len(session.state.players[pid].hand)>7: session.state.pending_discard_seq[pid]=response["seq_num"]
        elif typ=="PRIORITY_GRANT":
            target=response.get("player_id") or response.get("priority_player")
            if target is None: return
            response["player_id"]=target; response.pop("priority_player",None); response["time_limit_ms"]=int(response.get("time_limit_ms",self.priority_time_limit_ms))
            target_conn=next((c for c,i in self.clients.items() if i.get("player_id")==target),None)
            if target_conn is None: return
            conn=target_conn; session=self.game_server.get_player_session(target)
            sid=next((sid for sid,ss in self.game_server.sessions.items() if ss is session),"") if session else ""
            if response.pop("_reissue",False) and session is not None: seq=session.get_priority_seq_num()
            else:
                seq=self._next_server_seq()
                if session is not None: session.priority.set_priority_seq_num(seq)
            response["seq_num"]=seq
            if sid: self.priority_deadlines[sid]=time.monotonic()+response["time_limit_ms"]/1000.0
        elif typ in {"TRIGGER_CHOICE","TRIGGER_ORDER"}:
            target=response.get("player_id"); target_conn=next((c for c,i in self.clients.items() if i.get("player_id")==target),None)
            if target_conn is None: return
            conn=target_conn; response["seq_num"]=self._next_server_seq(); session=self.game_server.get_player_session(target)
            if session is not None:
                if typ=="TRIGGER_CHOICE": session.state.pending_trigger_choice_seq[target]=response["seq_num"]
                else: session.state.pending_trigger_order_seq[target]=response["seq_num"]
        elif typ=="ERROR":
            response.pop("error",None)
            response["seq_num"] = self._next_server_seq()
        else:
            response["seq_num"]=self._next_server_seq()
            if typ=="PHASE_TRANSITION" and response.get("to_phase") in {"DECLARE_ATTACKERS","DECLARE_BLOCKERS","ASSIGN_DAMAGE_ORDER"}:
                for session in self.game_server.sessions.values():
                    if session.state.phase==response["to_phase"]:
                        session.state.phase_action_seq=response["seq_num"]; session.state.phase_decision_complete=False
        send_pdu(conn,response); self.logger.log_pdu("S->C",response)

    # ================================================================
    # BROADCAST
    # ================================================================

    def broadcast(self, pdu: dict):
        """
        Send a server PDU to all connected clients.

        NOTE:
        Broadcast messages use transport sequence numbers only.
        They do not modify GameState.server_seq_num because an action
        sequence must not be made dependent on which client happened
        to receive a broadcast first.
        """

        response = dict(pdu)

        response["seq_num"] = self._next_server_seq()
        if response.get("type") == "PHASE_TRANSITION":
            to_phase = response.get("to_phase")
            if to_phase in {"DECLARE_ATTACKERS", "DECLARE_BLOCKERS", "ASSIGN_DAMAGE_ORDER"}:
                # The phase transition itself is the action token for the declaration PDU.
                for sid, session in self.game_server.sessions.items():
                    if session.state.phase == to_phase:
                        session.state.phase_action_seq = response["seq_num"]
                        session.state.phase_decision_complete = False
        for conn in list(self.clients.keys()):
            try:
                send_pdu(
                    conn,
                    response,
                )
                if conn in self.clients:
                    self.clients[conn]["last_server_seq"] = response.get("seq_num", self.clients[conn].get("last_server_seq", 0))

                self.logger.log_pdu(
                    "S->ALL",
                    response,
                )

            except Exception:
                self._handle_disconnect(
                    conn
                )

    def _emit_pending_trigger_requests(self,session):
        # Target/optional trigger choices must be resolved before priority.
        for pid,pending in list(session.state.pending_trigger_choices.items()):
            conn=next((c for c,i in self.clients.items() if i.get("player_id")==pid),None)
            if conn is None: continue
            self._send_response(conn,{"type":"TRIGGER_CHOICE","player_id":pid,"trigger_id":pending["trigger_id"],"source_id":pending["item"]["source_id"],"effect_summary":pending["effect_summary"],"requires_target":pending["requires_target"],"legal_targets":list(pending.get("legal_targets",[]))})
            return True
        # Then ask each controller to order simultaneous triggers.
        for pid,pending in list(session.state.pending_trigger_orders.items()):
            conn=next((c for c,i in self.clients.items() if i.get("player_id")==pid),None)
            if conn is None: continue
            self._send_response(conn,{"type":"TRIGGER_ORDER","player_id":pid,"trigger_ids":list(pending["trigger_ids"])})
            return True
        return False

    def _check_timeouts(self):
        now=time.monotonic()
        for sid,deadline in list(self.priority_deadlines.items()):
            if now<deadline: continue
            self.priority_deadlines.pop(sid,None); session=self.game_server.sessions.get(sid)
            if session is None or session.state.game_over or session.state.priority_player is None: continue
            loser=session.state.priority_player; winner=next((pid for pid in session.state.players if pid!=loser),None)
            session.state.game_over=True; session.state.winner=winner; session.state.game_over_reason="DISCONNECT"; session.state.priority_player=None
            self.broadcast({"type":"GAME_OVER","winner_id":winner,"loser_id":loser,"reason":"DISCONNECT"}); self.game_server.reset_session(sid)
        for pid,(sid,deadline) in list(self.disconnect_deadlines.items()):
            if now<deadline: continue
            self.disconnect_deadlines.pop(pid,None); session=self.game_server.sessions.get(sid)
            if session is None or session.state.game_over: continue
            winner=next((p for p in session.state.players if p!=pid),None)
            session.state.game_over=True; session.state.winner=winner; session.state.game_over_reason="DISCONNECT"; session.state.priority_player=None
            self.priority_deadlines.pop(sid,None); self.broadcast({"type":"GAME_OVER","winner_id":winner,"loser_id":pid,"reason":"DISCONNECT"}); self.game_server.reset_session(sid)

    # ================================================================
    # ERRORS
    # ================================================================

    def _send_error(
        self,
        conn,
        seq_num: int,
        code: str,
        message: str,
        rejected_action: dict = None,
    ):
        """
        Send an ERROR PDU without crashing the server.
        """

        error_pdu = build_error(
            self._next_server_seq(),
            code,
            message,
            rejected_action,
        )

        try:
            send_pdu(
                conn,
                error_pdu,
            )

            self.logger.log_pdu(
                "S->C",
                error_pdu,
            )

        except Exception:
            pass

    # ================================================================
    # DISCONNECT
    # ================================================================

    def _handle_disconnect(self, conn):
        """
        Handle a dropped TCP connection.
        """

        client_info = self.clients.get(conn)

        if client_info is None:
            return

        player_id = client_info.get(
            "player_id"
        )

        print(
            "Client disconnected"
            + (
                f": {player_id}"
                if player_id
                else ""
            )
        )

        # If this client established a game identity,
        # remove the GameServer association.
        if player_id:
            session=self.game_server.get_player_session(player_id)
            if session is not None and not session.state.game_over and len(session.state.players) == 2:
                sid=self.game_server.player_sessions.get(player_id)
                if sid: self.disconnect_deadlines[player_id]=(sid,time.monotonic()+10.0)
        try:
            conn.close()
        except Exception:
            pass

        self.clients.pop(
            conn,
            None,
        )

    # ================================================================
    # SHUTDOWN
    # ================================================================

    def stop(self):
        """
        Gracefully shut down the server and close
        all client connections.
        """

        if not self.running:
            return

        print(
            "Shutting down server..."
        )

        self.running = False

        for conn in list(
            self.clients.keys()
        ):
            try:
                conn.close()
            except Exception:
                pass

        self.clients.clear()

        if self.server_sock:
            try:
                self.server_sock.close()

                print(
                    "Server socket closed."
                )

            except Exception as e:
                print(
                    f"Error closing server socket: {e}"
                )

            self.server_sock = None