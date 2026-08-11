"""End-to-end heartbeat regression using the real MTGNPClient class."""
import socket
import threading
import time

import mtgnp.client.socket_client as client_module
from mtgnp.client.socket_client import MTGNPClient
from mtgnp.client.heartbeat import HeartbeatMonitor
from mtgnp.server.socket_server import MTGNPServer


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    port = free_port()
    server = MTGNPServer(host="127.0.0.1", port=port, verbose=False)
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.15)

    # Use the production MTGNPClient, but shorten the production heartbeat
    # interval for the regression test so it finishes quickly.
    class FastHeartbeat(HeartbeatMonitor):
        def __init__(self, *args, **kwargs):
            kwargs["ping_interval"] = 0.25
            kwargs["timeout"] = 1.0
            super().__init__(*args, **kwargs)

    original_hb = client_module.HeartbeatMonitor
    client_module.HeartbeatMonitor = FastHeartbeat

    clients = [
        MTGNPClient("127.0.0.1", port, "player_1", verbose=False),
        MTGNPClient("127.0.0.1", port, "player_2", verbose=False),
    ]
    for client in clients:
        client._stdin_loop = lambda c=client: (time.sleep(0.01) if c.running else None)

    threads = [threading.Thread(target=c.connect, daemon=True) for c in clients]
    for t in threads:
        t.start()
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if all(c._heartbeat_started and c.heartbeat and c.heartbeat.seq_num >= 3 for c in clients):
                break
            time.sleep(0.05)

        for c in clients:
            assert c.connected, f"{c.player_id} disconnected during idle heartbeat test"
            assert c._heartbeat_started, f"{c.player_id} heartbeat did not start after initial state"
            assert c.heartbeat.seq_num >= 3, f"{c.player_id} did not complete multiple heartbeats"
            assert c.engine.phase in {"LOBBY", "MULLIGAN"}, f"Unexpected phase for {c.player_id}: {c.engine.phase}"
        print("PASS: two real MTGNPClients completed idle PING/PONG heartbeats without disconnecting")
    finally:
        for client in clients:
            client.running = False
            client.connected = False
            if client.heartbeat:
                client.heartbeat.stop()
            try:
                if client.sock:
                    client.sock.close()
            except OSError:
                pass
        client_module.HeartbeatMonitor = original_hb
        server.stop()
        server_thread.join(timeout=2)


if __name__ == "__main__":
    main()
