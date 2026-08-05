import argparse
from mtgnp.server.socket_server import MTGNPServer

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTGNP Game Server[cite: 1]")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=4444, help="Server TCP port")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose PDU logging")

    args = parser.parse_args()
    server = MTGNPServer(host=args.host, port=args.port, verbose=args.verbose)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nServer shutting down gracefully.")
    finally:
        server.stop()