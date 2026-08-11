"""Runtime regression test for MTGNP PING/PONG over the real server."""

import socket
import threading
import time

from mtgnp.client.heartbeat import HeartbeatMonitor
from mtgnp.common.framing import recv_pdu
from mtgnp.server.socket_server import MTGNPServer


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def main():
    port = _free_port()
    server = MTGNPServer(host="127.0.0.1", port=port, verbose=False)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    time.sleep(0.15)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    sock.connect(("127.0.0.1", port))

    heartbeat = HeartbeatMonitor(
        sock,
        ping_interval=0.2,
        timeout=1.0,
    )
    heartbeat.start()

    # The real server must answer at least two heartbeats while no game
    # messages are being exchanged. This reproduces the idle-LOBBY case.
    deadline = time.monotonic() + 2.0
    pong_count = 0
    while time.monotonic() < deadline and pong_count < 2:
        pdu = recv_pdu(sock)
        if pdu is None:
            raise AssertionError("Server closed heartbeat connection")
        if pdu.get("type") == "PONG":
            pong_count += 1
            heartbeat.receive_pong(int(pdu.get("seq_num", 0)))

    heartbeat.stop()
    try:
        sock.close()
    finally:
        server.stop()

    assert pong_count >= 2, f"Expected at least 2 PONGs, got {pong_count}"
    print("PASS: real server responded to two client heartbeat PINGs")


if __name__ == "__main__":
    main()
