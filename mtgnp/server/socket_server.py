import socket
import select
from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger

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

    def broadcast(self, pdu: dict):
        """Sends a server PDU to all connected players."""
        pdu["seq_num"] = self.server_seq_num
        self.server_seq_num += 1
        for conn in self.clients.values():
            send_pdu(conn, pdu)
            self.logger.log_pdu("S->ALL", pdu)

    def stop(self):
        """Gracefully shuts down the server and closes all client connections."""
        if not self.running:
            return

        print("Shutting down server...")
        self.running = False

        # 1. Close all active client connections
        for player_id, conn in self.clients.items():
            try:
                conn.close()
                print(f"Closed connection for player {player_id}")
            except Exception as e:
                print(f"Error closing connection for player {player_id}: {e}")
        self.clients.clear()

        # 2. Close the main server listening socket
        if self.server_sock:
            try:
                self.server_sock.close()
                print("Server socket closed.")
            except Exception as e:
                print(f"Error closing server socket: {e}")
            self.server_sock = None