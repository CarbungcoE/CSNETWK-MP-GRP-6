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

    def start(self):
        self.running = True
        # Store on self so self.stop() can close it
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(2)
        print(f"Server started on {self.host}:{self.port}. Verbose={self.verbose}")

        # Wait for exactly 2 clients
        try:
        # Phase 1: Connection Phase (Wait for 2 clients)
            while len(self.clients) < 2 and self.running:
                readable, _, _ = select.select([self.server_sock], [], [], 1)
                for s in readable:
                    if s is self.server_sock:
                        conn, addr = self.server_sock.accept()
                        player_id = f"player_{len(self.clients) + 1}"
                        self.clients[player_id] = conn
                        print(f"Player {player_id} connected from {addr}.")

            print("Both players connected. Starting game loop...")

            # Phase 2: Main Game / Communication Loop
            while self.running:
                # Monitor all connected player sockets + listening socket
                sockets_to_watch = [self.server_sock] + list(self.clients.values())
                readable, _, _ = select.select(sockets_to_watch, [], [], 1)
                
                for s in readable:
                    if s is self.server_sock:
                        # Handle any additional incoming connection attempts
                        conn, _ = self.server_sock.accept()
                        conn.close()  # Reject extra connections if game is full
                    else:
                        # Handle incoming client PDUs
                        self._handle_client_data(s)

        except KeyboardInterrupt:
            print("\nShutdown signal received.")
        finally:
            self.stop()

    def _handle_client_data(self, conn):
        try:
            pdu = recv_pdu(conn)
            if not pdu:
                self._handle_disconnect(conn)
                return
            
            # find which player sent this
            player_id = [pid for pid, c in self.clients.items() if c == conn][0]
            self.logger.log_pdu("C->S", pdu)

            pdu_type = pdu.get("type")
            
            # handle Heartbeat immediately
            if pdu_type == "PING":
                # server echoes the timestamp back to the client
                pong = build_pong(pdu.get("seq_num", 0), pdu.get("timestamp", 0))
                send_pdu(conn, pong)
                self.logger.log_pdu("S->C", pong)
                return

            # hand off to PDU Dispatcher / Game State Machine here
            # self.dispatcher.dispatch(conn, pdu)

        except ValueError as ve:
            # handles MAX_PDU_SIZE exceeded or invalid JSON
            print(f"Framing/Value error: {ve}")
            self._send_error(conn, 0, "INVALID_JSON", str(ve))
        except ConnectionResetError:
            self._handle_disconnect(conn)
        except Exception as e:
            print(f"Unexpected error receiving data: {e}")
            self._handle_disconnect(conn)

    def broadcast(self, pdu: dict):
        """Sends a server PDU to all connected players."""
        pdu["seq_num"] = self.server_seq_num
        self.server_seq_num += 1
        for conn in self.clients.values():
            send_pdu(conn, pdu)
            self.logger.log_pdu("S->ALL", pdu)

    def _send_error(self, conn, seq_num: int, code: str, message: str, rejected_action: dict = None):
        """Sends an ERROR PDU to a specific client without crashing the server."""
        error_pdu = build_error(seq_num, code, message, rejected_action)
        try:
            send_pdu(conn, error_pdu)
            self.logger.log_pdu("S->C", error_pdu)
        except Exception:
            pass # client is likely already dead if this fails

    def _handle_disconnect(self, conn):
        """Handles dropped TCP connections, declares a winner, and cleans up."""
        disconnected_player = None
        for pid, c in list(self.clients.items()):
            if c == conn:
                disconnected_player = pid
                break
        
        if disconnected_player:
            print(f"Player {disconnected_player} disconnected unexpectedly.")
            
            # the remaining player wins by default
            winner_id = "player_1" if disconnected_player == "player_2" else "player_2"
            
            # broadcast GAME_OVER due to DISCONNECT
            game_over_pdu = build_game_over(self.server_seq_num, winner_id, disconnected_player, "DISCONNECT")
            self.broadcast(game_over_pdu)
            
            # clean up the dead socket
            conn.close()
            del self.clients[disconnected_player]
            
            # return to LOBBY state

    def stop(self):
        """Gracefully shuts down the server and closes all client connections."""
        if not self.running:
            return

        print("Shutting down server...")
        self.running = False

        # close all active client connections
        for player_id, conn in self.clients.items():
            try:
                conn.close()
                print(f"Closed connection for player {player_id}")
            except Exception as e:
                print(f"Error closing connection for player {player_id}: {e}")
        self.clients.clear()

        # close the main server listening socket
        if self.server_sock:
            try:
                self.server_sock.close()
                print("Server socket closed.")
            except Exception as e:
                print(f"Error closing server socket: {e}")
            self.server_sock = None