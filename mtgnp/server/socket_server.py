import socket
import select

from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger
from mtgnp.common.pdu import build_pong, build_error, build_game_over

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

        self.server_seq_num = 1
        self.running = False
        self.server_sock = None

        # Socket connections are tracked independently from
        # protocol-level player identities.
        self.clients = {}  # {socket_conn: connection_info}

        self.game_server = GameServer()
        self.dispatcher = Dispatcher(self.game_server)

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
                sockets_to_watch = [
                    self.server_sock
                ] + list(self.clients.keys())

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

            # Heartbeat is handled at the transport layer.
            if pdu_type == "PING":
                pong = build_pong(
                    pdu.get("seq_num", 0),
                    pdu.get("timestamp", 0),
                )

                send_pdu(conn, pong)

                self.logger.log_pdu(
                    "S->C",
                    pong,
                )

                return

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

                if response is not None:
                    client_info["player_id"] = player_id
                    self._send_response(conn, response)

                return

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
                self._send_response(
                    conn,
                    response,
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

        except Exception as e:
            print(
                f"Unexpected error receiving data: {e}"
            )

            self._handle_disconnect(conn)

    def _send_response(
        self,
        conn,
        pdu: dict,
    ):
        """
        Send a dispatcher response to one client.
        """
        response = dict(pdu)

        response.setdefault(
            "seq_num",
            self.server_seq_num,
        )

        if "seq_num" not in pdu:
            self.server_seq_num += 1

        send_pdu(
            conn,
            response,
        )

        self.logger.log_pdu(
            "S->C",
            response,
        )

    def broadcast(self, pdu: dict):
        """
        Send a server PDU to all connected clients.
        """
        response = dict(pdu)

        response["seq_num"] = (
            self.server_seq_num
        )

        self.server_seq_num += 1

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
            f"Client disconnected"
            + (
                f": {player_id}"
                if player_id
                else ""
            )
        )

        # If this client had established a game identity,
        # remove the GameServer association.
        if player_id:
            self.game_server.leave_session(
                player_id
            )

        try:
            conn.close()
        except Exception:
            pass

        del self.clients[conn]

    def stop(self):
        """
        Gracefully shut down the server and close
        all client connections.
        """
        if not self.running:
            return

        print("Shutting down server...")

        self.running = False

        for conn in list(self.clients.keys()):
            try:
                conn.close()
            except Exception:
                pass

        self.clients.clear()

        if self.server_sock:
            try:
                self.server_sock.close()
                print("Server socket closed.")
            except Exception as e:
                print(
                    f"Error closing server socket: {e}"
                )

            self.server_sock = None