from mtgnp.client.socket_client import MTGNPClient


def test_mulligan_keep_clears_server_wait_guard():
    client = MTGNPClient("127.0.0.1", 4444, "player_1", False)
    client._waiting_for_server_input = True
    client.mulligan_waiting_for_state = True
    client.input_context = {"kind": "mulligan_keep"}

    client._handle_pdu({"type": "MULLIGAN_RESULT", "kept": True, "seq_num": 7})

    assert client._waiting_for_server_input is False
    assert client.mulligan_waiting_for_state is False
    assert client.input_context is None
    assert client.engine.mulligan_kept is True


def test_leaving_mulligan_clears_guard_even_if_result_arrival_was_raced():
    client = MTGNPClient("127.0.0.1", 4444, "player_1", False)
    client._waiting_for_server_input = True
    client.mulligan_waiting_for_state = True

    client._handle_pdu({
        "type": "GAME_STATE_UPDATE",
        "seq_num": 20,
        "state": {
            "phase": "UPKEEP",
            "turn": 1,
            "active_player": "player_1",
            "priority_player": "player_1",
            "priority_seq_num": 21,
            "mulligan_count": 0,
            "mulligan_kept": True,
            "life_totals": {"player_1": 20, "player_2": 20},
            "hand": [],
            "hand_counts": {"player_1": 0, "player_2": 0},
            "library_counts": {"player_1": 0, "player_2": 0},
            "battlefield": {"player_1": [], "player_2": []},
            "graveyard": {"player_1": [], "player_2": []},
            "stack": [],
        },
    })

    assert client._waiting_for_server_input is False
    assert client.mulligan_waiting_for_state is False
