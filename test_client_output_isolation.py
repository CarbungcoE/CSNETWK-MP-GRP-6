"""Regression tests for client terminal-output isolation during active prompts."""

from contextlib import redirect_stdout
from io import StringIO

from mtgnp.client.socket_client import MTGNPClient


def state_update(phase="MULLIGAN", seq=10, active_player="player_2"):
    return {
        "type": "GAME_STATE_UPDATE",
        "seq_num": seq,
        "state": {
            "phase": phase,
            "active_player": active_player,
            "priority_holder": None,
            "life_totals": {"player_1": 20, "player_2": 20},
            "hand": ["mountain_001"],
            "hand_counts": {"player_1": 7, "player_2": 7},
            "library_counts": {"player_1": 1, "player_2": 1},
            "battlefield": {"player_1": [], "player_2": []},
            "graveyard": {"player_1": [], "player_2": []},
            "stack": [],
            "mulligan_count": 0,
            "mulligan_kept": False,
            "mulligan_status": {},
        },
    }


def main():
    client = MTGNPClient("127.0.0.1", 4444, "player_1", False)

    # While player_1 is answering a local prompt, an unrelated state update
    # from player_2 must update the engine silently instead of redrawing the
    # board over player_1's prompt.
    client.input_context = {"kind": "mulligan_keep"}
    out = StringIO()
    with redirect_stdout(out):
        client._handle_pdu(state_update())
    assert out.getvalue() == ""
    assert client.engine.phase == "MULLIGAN"
    assert client.engine.active_player == "player_2"

    # Likewise, a remote priority grant must not overwrite the local prompt.
    out = StringIO()
    with redirect_stdout(out):
        client._handle_pdu({
            "type": "PRIORITY_GRANT",
            "seq_num": 11,
            "player_id": "player_2",
            "priority_player": "player_2",
            "time_limit_ms": 60000,
        })
    assert out.getvalue() == ""

    # Once the local interaction is finished, the client may print the
    # resulting server update normally.
    client.input_context = None
    out = StringIO()
    with redirect_stdout(out):
        client._handle_pdu(state_update(phase="UPKEEP", seq=12, active_player="player_1"))
    assert "PHASE: UPKEEP" in out.getvalue()

    print("PASS: client output stays isolated while a local interaction is active")


if __name__ == "__main__":
    main()
