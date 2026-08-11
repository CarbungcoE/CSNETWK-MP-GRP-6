from mtgnp.client.socket_client import MTGNPClient

def test_empty_payment_uses_card_required_colors():
    client = MTGNPClient("127.0.0.1", 4444, "player_1", False)
    client._card = lambda card_id: {"R": 1, "Generic": 2}
    assert client._parse_payment("", "test-card") == {"R": 1, "C": 2}
