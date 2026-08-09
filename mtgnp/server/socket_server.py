import socket
import select
from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger
from mtgnp.common.pdu import build_pong, build_error, build_game_over

class MTGNPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 4444, verbose: bool = False):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.logger = VerboseLogger(enabled=verbose, label="SERVER")
        self.server_seq_num = 1
        self.running = False
        self.server_sock = None
        self.clients = {}  # {player_id: socket_conn}
        self.dispatcher = None  # To be connected to Game State Machine / Dispatcher

    def start(self):
        self.running = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(2)
        print(f"Server started on {self.host}:{self.port}. Verbose={self.verbose}")

        try:
            while self.running:
                # Phase 1: Wait for exactly 2 players in LOBBY
                if len(self.clients) < 2:
                    self._wait_for_players()
                    if not self.running:
                        break
                    print("Both players connected. Transitioning to game session...")

                # Phase 2: Active Session Loop
                self._run_game_loop()

        except KeyboardInterrupt:
            print("\nShutdown signal received.")
        finally:
            self.stop()

    def _wait_for_players(self):
        """Blocks until 2 players are connected."""
        while len(self.clients) < 2 and self.running:
            readable, _, _ = select.select([self.server_sock], [], [], 0.5)
            for s in readable:
                if s is self.server_sock:
                    conn, addr = self.server_sock.accept()
                    conn.settimeout(2.0)  # Prevent indefinite blocking in framing
                    player_id = "player_1" if "player_1" not in self.clients else "player_2"
                    self.clients[player_id] = conn
                    print(f"Player {player_id} connected from {addr}.")

    def _run_game_loop(self):
        """Monitors active connections during game session."""
        while len(self.clients) == 2 and self.running:
            sockets_to_watch = [self.server_sock] + list(self.clients.values())
            readable, _, _ = select.select(sockets_to_watch, [], [], 0.5)

            for s in readable:
                if s is self.server_sock:
                    # Reject extra incoming connections when session is full
                    conn, _ = self.server_sock.accept()
                    conn.close()
                else:
                    self._handle_client_data(s)

    def _handle_client_data(self, conn):
        player_id = next((pid for pid, c in self.clients.items() if c == conn), None)
        if not player_id:
            return

        try:
            pdu = recv_pdu(conn)
            if not pdu:
                self._handle_disconnect(player_id)
                return

            self.logger.log_pdu("C->S", pdu)
            pdu_type = pdu.get("type")

            # Immediately answer ping heartbeats
            if pdu_type == "PING":
                pong = build_pong(pdu.get("seq_num", 0), pdu.get("timestamp", 0))
                self.send_to_client(player_id, pong)
                return

            # Hand off to game engine dispatcher
            if self.dispatcher:
                self.dispatcher.dispatch(player_id, pdu)

        except (ValueError, socket.timeout) as e:
            print(f" Framing/Protocol error from {player_id}: {e}")
            self._send_error(conn, 0, "INVALID_JSON", str(e))
        except (ConnectionResetError, BrokenPipeError):
            self._handle_disconnect(player_id)
        except Exception as e:
            print(f"Unexpected error handling {player_id}: {e}")
            self._handle_disconnect(player_id)

    def send_to_client(self, player_id: str, pdu: dict):
        """Sends a unicast server PDU with assigned server sequence number."""
        conn = self.clients.get(player_id)
        if not conn:
            return

        pdu["seq_num"] = self.server_seq_num
        self.server_seq_num += 1

        try:
            send_pdu(conn, pdu)
            self.logger.log_pdu(f"S->{player_id.upper()}", pdu)
        except (ConnectionResetError, BrokenPipeError):
            self._handle_disconnect(player_id)

    def broadcast(self, pdu: dict):
        """Broadcasts a PDU to all currently connected players."""
        pdu["seq_num"] = self.server_seq_num
        self.server_seq_num += 1

        dead_players = []
        for player_id, conn in list(self.clients.items()):
            try:
                send_pdu(conn, pdu)
                self.logger.log_pdu(f"S->{player_id.upper()}", pdu)
            except (ConnectionResetError, BrokenPipeError):
                dead_players.append(player_id)

        for pid in dead_players:
            self._handle_disconnect(pid)

    def _send_error(self, conn, seq_num: int, code: str, message: str, rejected_action: dict = None):
        error_pdu = build_error(seq_num, code, message, rejected_action)
        try:
            send_pdu(conn, error_pdu)
            self.logger.log_pdu("S->C", error_pdu)
        except Exception:
            pass

    def _handle_disconnect(self, disconnected_player: str):
        """Cleans up disconnected player socket and notifies surviving player."""
        conn = self.clients.pop(disconnected_player, None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            print(f"Player {disconnected_player} disconnected.")

        # Notify remaining player of victory
        if self.clients:
            winner_id = list(self.clients.keys())[0]
            game_over_pdu = build_game_over(self.server_seq_num, winner_id, disconnected_player, "DISCONNECT")
            self.broadcast(game_over_pdu)

    def stop(self):
        if not self.running:
            return

        print("Shutting down server...")
        self.running = False

        for player_id, conn in list(self.clients.items()):
            try:
                conn.close()
            except Exception:
                pass
        self.clients.clear()

        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None