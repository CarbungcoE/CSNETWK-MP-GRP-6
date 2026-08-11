"""Regression test: PRIORITY_GRANT seq_num must match visible state.priority_seq_num."""

import select
import socket
import threading
import time

from mtgnp.common.framing import recv_pdu, send_pdu
from mtgnp.common.pdu import build_mulligan_choice, build_player_ready, build_priority_pass
from mtgnp.server.socket_server import MTGNPServer


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _send_ready(sock, pid):
    pdu = build_player_ready(1, pid, [
        "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
        "shock_001", "shock_002", "goblin_guide_001",
        "mountain_001", "mountain_002",
    ])
    pdu["session_id"] = "runtime-sync"
    send_pdu(sock, pdu)


def _recv_until(sock, wanted, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pdu = recv_pdu(sock)
        if pdu is None:
            raise AssertionError("server closed connection")
        if pdu.get("type") == wanted:
            return pdu
    raise AssertionError(f"timed out waiting for {wanted}")


def main():
    port = _free_port()
    server = MTGNPServer("127.0.0.1", port, verbose=False)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    time.sleep(0.15)

    p1 = socket.create_connection(("127.0.0.1", port))
    p2 = socket.create_connection(("127.0.0.1", port))
    socks = {p1: "player_1", p2: "player_2"}

    try:
        _send_ready(p1, "player_1")
        _recv_until(p1, "GAME_STATE_UPDATE")
        _send_ready(p2, "player_2")
        s1 = _recv_until(p1, "GAME_STATE_UPDATE")
        s2 = _recv_until(p2, "GAME_STATE_UPDATE")

        send_pdu(p1, build_mulligan_choice(s1["seq_num"], True, []))
        send_pdu(p2, build_mulligan_choice(s2["seq_num"], True, []))

        # Drive the automatic priority cycle until a grant is observed,
        # passing every grant. Track the state snapshot for the same player.
        pending_grant = None
        latest_state = {}
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            readable, _, _ = select.select([p1, p2], [], [], 1)
            for sock in readable:
                pdu = recv_pdu(sock)
                if pdu is None:
                    raise AssertionError("server closed connection")
                typ = pdu.get("type")
                if typ == "GAME_STATE_UPDATE":
                    latest_state[socks[sock]] = pdu["state"]
                elif typ == "PRIORITY_GRANT":
                    pending_grant = pdu
                    pid = pdu["player_id"]
                    state = latest_state.get(pid)
                    if state is not None:
                        assert state["priority_seq_num"] == pdu["seq_num"], (
                            f"priority seq mismatch for {pid}: "
                            f"state={state['priority_seq_num']} grant={pdu['seq_num']}"
                        )
                    send_pdu(sock, build_priority_pass(pdu["seq_num"]))
                if pending_grant and latest_state.get(pending_grant["player_id"]):
                    # We only need one successful state/grant pair.
                    state = latest_state[pending_grant["player_id"]]
                    if state.get("priority_seq_num") == pending_grant["seq_num"]:
                        print("PASS: PRIORITY_GRANT seq matches GAME_STATE_UPDATE state")
                        return
        raise AssertionError("did not observe a matching priority grant/state pair")
    finally:
        p1.close(); p2.close(); server.stop()


if __name__ == "__main__":
    main()
