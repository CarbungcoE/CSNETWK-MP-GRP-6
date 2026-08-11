"""Regression tests for interactive prompts and heartbeat coexistence."""
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


class FastHeartbeat(HeartbeatMonitor):
    def __init__(self, *args, **kwargs):
        kwargs["ping_interval"] = 0.2
        kwargs["timeout"] = 0.5
        kwargs["max_missed_heartbeats"] = 2
        super().__init__(*args, **kwargs)


def main():
    port = free_port()
    server = MTGNPServer(host="127.0.0.1", port=port, verbose=False)
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.15)

    original_hb = client_module.HeartbeatMonitor
    client_module.HeartbeatMonitor = FastHeartbeat
    clients = [
        MTGNPClient("127.0.0.1", port, "player_1", verbose=False),
        MTGNPClient("127.0.0.1", port, "player_2", verbose=False),
    ]
    for c in clients:
        c._stdin_loop = lambda c=c: (time.sleep(0.01) if c.running else None)

    threads = [threading.Thread(target=c.connect, daemon=True) for c in clients]
    for t in threads:
        t.start()

    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not all(c._heartbeat_started for c in clients):
            time.sleep(0.05)

        assert all(c.connected for c in clients), "A client disconnected during startup"
        assert all(c._heartbeat_started for c in clients), "Heartbeat did not start"

        # Simulate one client being inside a local multi-step prompt. Remote state
        # updates must still update the engine but must not replace the local prompt.
        c = clients[0]
        c.input_context = {"kind": "mulligan_keep"}
        c._deferred_output = []
        c._print_line("REMOTE PHASE UPDATE")
        assert c._deferred_output == ["REMOTE PHASE UPDATE"]
        c.input_context = None
        c._flush_deferred_output()

        # Give both clients enough time for multiple real PING/PONG exchanges.
        time.sleep(1.5)
        assert all(c.connected for c in clients), "Client disconnected during interactive heartbeat window"
        assert all(c.heartbeat.seq_num >= 3 for c in clients), "Expected multiple heartbeat cycles"
        print("PASS: interactive prompt state coexists with real PING/PONG heartbeats")
    finally:
        for c in clients:
            c.running = False
            c.connected = False
            if c.heartbeat:
                c.heartbeat.stop()
            try:
                if c.sock:
                    c.sock.close()
            except OSError:
                pass
        client_module.HeartbeatMonitor = original_hb
        server.stop()
        server_thread.join(timeout=2)


if __name__ == "__main__":
    main()
