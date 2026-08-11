"""Top-level entry point for the real interactive MTGNP player client."""

from mtgnp.client.socket_client import MTGNPClient


def main():
    import argparse

    parser = argparse.ArgumentParser(description="MTGNP Player Client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host IP")
    parser.add_argument("--port", type=int, default=4444, help="Server TCP port")
    parser.add_argument("--id", required=True, help="Unique Player ID")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose PDU logging",
    )

    args = parser.parse_args()

    client = MTGNPClient(
        host=args.host,
        port=args.port,
        player_id=args.id,
        verbose=args.verbose,
        session_id=args.session_id,
    )
    client.connect()


if __name__ == "__main__":
    main()
