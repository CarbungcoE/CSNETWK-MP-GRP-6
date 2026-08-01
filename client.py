import argparse
import socket
import threading
from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger

class MTGNPClient:
    def __init__(self, host: str, port: int, player_id: str, verbose: bool):
        self.host = host
        self.port = port
        self.player_id = player_id
        self.logger = VerboseLogger(enabled=verbose, label=f"CLIENT ({player_id})")
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print(f"Connected to server {self.host}:{self.port}")

        # Start receive loop in separate thread
        threading.Thread(target=self._receive_loop, daemon=True).start()

    def _receive_loop(self):
        while True:
            try:
                pdu = recv_pdu(self.sock)
                if not pdu:
                    break
                self.logger.log_pdu("S->C", pdu)
                self._handle_pdu(pdu)
            except Exception as e:
                print(f"Connection lost: {e}")
                break

    def _handle_pdu(self, pdu: dict):
        # Route logic according to pdu["type"]
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTGNP Player Client[cite: 1]")
    parser.add_argument("--host", default="127.0.0.1", help="Server host IP")
    parser.add_argument("--port", type=int, default=4444, help="Server port")
    parser.add_argument("--id", required=True, help="Unique Player ID")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose PDU logging")

    args = parser.parse_args()
    client = MTGNPClient(host=args.host, port=args.port, player_id=args.id, verbose=args.verbose)
    client.connect()