"""Regression tests for the two-step London mulligan client/server flow."""
from mtgnp.server.game_session import GameSession

DECK = [
    "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
    "shock_001", "shock_002", "goblin_guide_001",
    "mountain_001", "mountain_002",
]

def make_session():
    session = GameSession()
    ok, err, _ = session.player_ready("player_1", DECK)
    assert ok and not err
    ok, err, _ = session.player_ready("player_2", DECK)
    assert ok and not err
    assert session.state.phase == "MULLIGAN"
    return session

def main():
    # Normal two-step flow.
    session = make_session()

    # First hand: keeping immediately requires zero cards to bottom.
    ok, err = session.process_mulligan("player_1", True, [])
    assert ok and not err
    assert session.state.players["player_1"].kept_hand is True

    # Rejecting a hand never supplies bottom cards in the same PDU.
    ok, err = session.process_mulligan("player_2", False, [])
    assert ok and not err
    assert session.state.players["player_2"].mulligan_count == 1
    assert len(session.state.players["player_2"].hand) == 7

    # After the replacement hand is dealt, keeping requires exactly
    # one card to be bottomed.
    ok, err = session.process_mulligan("player_2", True, [])
    assert not ok and err == "ILLEGAL_ACTION"

    card = session.state.players["player_2"].hand[0]
    ok, err = session.process_mulligan("player_2", True, [card])
    assert ok and not err
    assert session.state.players["player_2"].kept_hand is True

    # MTGNP deliberately permits repeated mulligans. After enough mulligans,
    # the RFC's exact-N bottoming rule becomes impossible because a redraw
    # still contains only seven cards. The server must reject that keep rather
    # than inventing a mulligan cap or silently changing the protocol.
    edge = make_session()
    for _ in range(8):
        ok, err = edge.process_mulligan("player_1", False, [])
        assert ok and not err
    assert edge.state.players["player_1"].mulligan_count == 8
    assert len(edge.state.players["player_1"].hand) == 7
    ok, err = edge.process_mulligan(
        "player_1",
        True,
        list(edge.state.players["player_1"].hand),
    )
    assert not ok and err == "ILLEGAL_ACTION"

    print("PASS: London mulligan two-step flow and unlimited-mulligan edge case are valid")

if __name__ == "__main__":
    main()
