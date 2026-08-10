import socket
import select

from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger
from mtgnp.common.pdu import (
    build_pong,
    build_error,
    build_phase_transition,
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

        self.clients[conn] = {
            "addr": addr,
            "player_id": None,
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

                if not player_id:
                    self._send_error(
                        conn,
                        0,
                        "MISSING_PLAYER_ID",
                        "PLAYER_READY requires player_id.",
                    )
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

                if (
                    session is not None
                    and session.state.phase == "MULLIGAN"
                ):
                    # One authoritative sequence number for the mulligan
                    # state shared by both players.
                    mulligan_seq = self.server_seq_num
                    self.server_seq_num += 1

                    for other_conn, other_info in list(
                        self.clients.items()
                    ):
                        other_player_id = other_info.get(
                            "player_id"
                        )

                        if other_player_id is None:
                            continue

                        state = session.get_visible_state(
                            other_player_id
                        )

                        state["priority_holder"] = None

                        # Store the exact sequence number that this player
                        # must echo in MULLIGAN_CHOICE.
                        session.set_mulligan_seq(
                            other_player_id,
                            mulligan_seq,
                        )

                        mulligan_pdu = {
                            "type": "GAME_STATE_UPDATE",
                            "seq_num": mulligan_seq,
                            "state": state,
                        }

                        send_pdu(
                            other_conn,
                            mulligan_pdu,
                        )

                        self.logger.log_pdu(
                            "S->C",
                            mulligan_pdu,
                        )

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
                if response.get("type") == "PRIORITY_PHASE_ADVANCED":
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

                        # The new priority window is authoritative. Send
                        # personalized state to both players so either
                        # client can continue the priority sequence.
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
                        session.start_game()

                        # UNTAP is an automatic phase with no priority.
                        # Advance to the first priority-bearing phase.
                        if session.state.phase == "UNTAP":
                            session.advance_phase()

                        # UPKEEP is the first phase where priority is
                        # required. Grant it to the active player.
                        if (
                            session.state.phase == "UPKEEP"
                            and session.state.priority_player is None
                        ):
                            session.grant_active_player_priority()

                        self._broadcast_game_state(session)

                    except ValueError as exc:
                        self._send_error(
                            conn,
                            0,
                            "GAME_START_FAILED",
                            str(exc),
                        )

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
        """
        Send the current authoritative state to every identified player.

        GAME_STATE_UPDATE sequence numbers are transport sequence numbers
        on the wire. The authoritative priority sequence remains inside
        GameState.priority_seq_num and is never replaced by this value.
        """
        for conn, client_info in list(self.clients.items()):
            target_player_id = client_info.get("player_id")

            if target_player_id is None:
                continue

            target_session = self.game_server.get_player_session(
                target_player_id
            )

            if target_session is not session:
                continue

            state = session.get_visible_state(target_player_id)

            self._send_response(
                conn,
                {
                    "type": "GAME_STATE_UPDATE",
                    "state": state,
                },
            )

    # ================================================================
    # SERVER -> CLIENT
    # ================================================================

    def _next_server_seq(self):
        """
        Get the next transport/server sequence number.

        IMPORTANT:
        This is NOT the game's authoritative action sequence.
        """
        seq_num = self.server_seq_num

        self.server_seq_num += 1

        return seq_num

    def _send_response(
        self,
        conn,
        pdu: dict,
    ):
        """
        Send a dispatcher response to one client.

        GAME_STATE_UPDATE is special:

        Its seq_num is also recorded in the player's GameState as
        the authoritative sequence that the client must echo for
        the next action.

        Non-state responses simply receive a transport sequence number.
        """

        if pdu is None:
            return

        response = dict(pdu)

        # ------------------------------------------------------------
        # GAME_STATE_UPDATE
        # ------------------------------------------------------------

        if response.get("type") == "GAME_STATE_UPDATE":
            client_info = self.clients.get(conn)

            player_id = None

            if client_info is not None:
                player_id = client_info.get("player_id")

            session = None

            if player_id:
                session = self.game_server.get_player_session(
                    player_id
                )

            if session is not None:
                #
                # This response is the authoritative state snapshot
                # for this player.
                #
                # Give it a fresh server sequence number.
                #
                seq_num = self._next_server_seq()

                response["seq_num"] = seq_num

                #
                # IMPORTANT:
                #
                # Store the exact same sequence number that we are
                # putting on the wire.
                #
                session.state.server_seq_num = seq_num

            else:
                # This should only happen for an unexpected state
                # response before the player has been associated.
                response["seq_num"] = self._next_server_seq()

        # ------------------------------------------------------------
        # OTHER SERVER RESPONSES
        # ------------------------------------------------------------

        elif response.get("type") == "PRIORITY_GRANT":
            # PRIORITY_GRANT is sent only to the player who now holds
            # priority. The seq_num here is the authoritative priority
            # token and must not be replaced by the transport sequence.
            target_player_id = response.get("priority_player")

            if target_player_id is not None:
                target_conn = None

                for candidate_conn, info in self.clients.items():
                    if info.get("player_id") == target_player_id:
                        target_conn = candidate_conn
                        break

                if target_conn is not None:
                    conn = target_conn

        else:
            response["seq_num"] = self._next_server_seq()

        send_pdu(
            conn,
            response,
        )

        self.logger.log_pdu(
            "S->C",
            response,
        )

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

        for conn in list(self.clients.keys()):
            try:
                send_pdu(
                    conn,
                    response,
                )

                self.logger.log_pdu(
                    "S->ALL",
                    response,
                )

            except Exception:
                self._handle_disconnect(
                    conn
                )

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
            seq_num,
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
            try:
                self.game_server.leave_session(
                    player_id
                )
            except Exception:
                pass

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