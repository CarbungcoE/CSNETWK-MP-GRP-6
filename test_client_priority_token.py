"""Regression test for client priority-token desynchronization.

A PRIORITY_GRANT carries the authoritative action token, while a later
GAME_STATE_UPDATE carries a separate transport/event sequence. The latter
must never overwrite the token used for PRIORITY_PASS/CAST/PLAY_LAND/etc.
"""

from mtgnp.client.engine import ClientEngine


def main():
    client = ClientEngine("player_1")

    client.set_priority({
        "type": "PRIORITY_GRANT",
        "player_id": "player_1",
        "seq_num": 14,
        "time_limit_ms": 60000,
    })
    assert client.seq_num == 14
    assert client.priority_seq_num == 14

    client.update_state({
        "type": "GAME_STATE_UPDATE",
        "seq_num": 15,
        "state": {
            "phase": "UPKEEP",
            "active_player": "player_1",
            "priority_player": "player_1",
            "priority_seq_num": 14,
            "life_totals": {"player_1": 20, "player_2": 20},
            "hand": [],
            "hand_counts": {"player_1": 0, "player_2": 0},
            "library_counts": {"player_1": 0, "player_2": 0},
            "battlefield": {"player_1": [], "player_2": []},
            "graveyard": {"player_1": [], "player_2": []},
            "stack": [],
        },
    })

    assert client.server_seq_num == 15
    assert client.priority_seq_num == 14
    assert client.seq_num == 14

    print("PASS: priority action token is not overwritten by GAME_STATE_UPDATE transport seq")


if __name__ == "__main__":
    main()
