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
        self.clients = {}  # {player_id: socket_conn}

    def start(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(2)
        print(f"Server started on {self.host}:{self.port}. Verbose={self.verbose}")

        # Wait for exactly 2 clients
        while len(self.clients) < 2:
            conn, addr = server_sock.accept()
            print(f"New connection from {addr}")
            # Registration/Handshake logic goes here ...

    def broadcast(self, pdu: dict):
        """Sends a server PDU to all connected players."""
        pdu["seq_num"] = self.server_seq_num
        self.server_seq_num += 1
        for conn in self.clients.values():
            send_pdu(conn, pdu)
            self.logger.log_pdu("S->ALL", pdu)