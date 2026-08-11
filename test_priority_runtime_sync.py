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
        first1 = _recv_until(p1, "GAME_STATE_UPDATE")
        _send_ready(p2, "player_2")
        # PLAYER_READY may yield a LOBBY update for player 1. Only the
        # authoritative MULLIGAN snapshot is valid for MULLIGAN_CHOICE.
        s1 = first1 if first1.get("state", {}).get("phase") == "MULLIGAN" else _recv_until(p1, "GAME_STATE_UPDATE")
        s2 = _recv_until(p2, "GAME_STATE_UPDATE")
        if s2.get("state", {}).get("phase") != "MULLIGAN":
            s2 = _recv_until(p2, "GAME_STATE_UPDATE")

        send_pdu(p1, build_mulligan_choice(s1["seq_num"], True, []))
        # A player keeping their hand causes a fresh GAME_STATE_UPDATE to be
        # broadcast to the other player, which refreshes that player's
        # mulligan sequence token. Always submit the latest MULLIGAN snapshot.
        latest_s2 = s2
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            readable, _, _ = select.select([p2], [], [], 0.1)
            if not readable:
                continue
            candidate = recv_pdu(p2)
            if candidate is None:
                raise AssertionError("server closed connection while refreshing player_2 mulligan state")
            if candidate.get("type") == "GAME_STATE_UPDATE" and candidate.get("state", {}).get("phase") == "MULLIGAN":
                latest_s2 = candidate
                if latest_s2.get("state", {}).get("mulligan_status", {}).get("player_1", {}).get("kept"):
                    break
        send_pdu(p2, build_mulligan_choice(latest_s2["seq_num"], True, []))

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
                    # The server may send the grant before the following
                    # GAME_STATE_UPDATE. Do not compare against an older
                    # snapshot; hold the token until a matching state arrives.
                    pending_grant = pdu
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
