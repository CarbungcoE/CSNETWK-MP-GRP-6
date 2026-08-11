"""Regression test: Dispatcher priority-pass handler initializes result before use."""

from mtgnp.server.dispatcher import Dispatcher
from mtgnp.server.game_server import GameServer


def main():
    server = GameServer()
    session = server.create_session("dispatcher-priority-regression")
    server.join_session("dispatcher-priority-regression", "player_1")
    server.join_session("dispatcher-priority-regression", "player_2")

    deck = [
        "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
        "shock_001", "shock_002", "goblin_guide_001",
        "mountain_001", "mountain_002",
    ]
    assert session.player_ready("player_1", deck)[0]
    assert session.player_ready("player_2", deck)[0]
    assert session.process_mulligan("player_1", True, [])[0]
    assert session.process_mulligan("player_2", True, [])[0]

    # Put the session in a valid priority window without involving sockets.
    session.state.phase = "UPKEEP"
    session.state.active_player = "player_1"
    session.grant_active_player_priority()
    seq = session.get_priority_seq_num()

    dispatcher = Dispatcher(server)
    response = dispatcher.handle_priority_pass("player_1", {"seq_num": seq})

    assert isinstance(response, dict)
    assert response.get("type") in {
        "PRIORITY_GRANT",
        "PRIORITY_PHASE_ADVANCED",
        "STACK_PRIORITY_RESOLVED",
    }
    print("PASS: dispatcher priority handler initializes result before result.get()")


if __name__ == "__main__":
    main()
