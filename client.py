import argparse
import socket
import threading
from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger
from mtgnp.client.socket_client import MTGNPClient

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTGNP Player Client[cite: 1]")
    parser.add_argument("--host", default="127.0.0.1", help="Server host IP")
    parser.add_argument("--port", type=int, default=4444, help="Server port")
    parser.add_argument("--id", required=True, help="Unique Player ID")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose PDU logging")

    args = parser.parse_args()
    client = MTGNPClient(host=args.host, port=args.port, player_id=args.id, verbose=args.verbose)
    client.connect()