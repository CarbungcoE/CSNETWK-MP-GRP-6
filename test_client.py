import socket

from mtgnp.common.framing import send_pdu, recv_pdu


HOST = "127.0.0.1"
PORT = 4444


def connect_player(player_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print(f"{player_id} connected")
    return sock


def send_ready(sock, player_id):
    pdu = {
        "type": "PLAYER_READY",
        "seq_num": 1,
        "session_id": "test-game",
        "player_id": player_id,
        "deck_list": [
            "lightning_bolt_001",
            "lightning_bolt_002",
            "lightning_bolt_003",
            "shock_001",
            "shock_002",
            "goblin_guide_001",
            "mountain_001",
            "mountain_002",
        ],
    }

    send_pdu(sock, pdu)
    print(f"{player_id} → PLAYER_READY")

def receive(sock, player_id):
    pdu = recv_pdu(sock)

    print(f"\n{player_id} received:")
    print(pdu)

    return pdu

def send_mulligan_keep(sock, player_id):
    pdu = {
        "type": "MULLIGAN_CHOICE",
        "seq_num": 2,
        "session_id": "test-game",
        "player_id": player_id,
        "keep": True,
        "cards_to_bottom": [],
    }

    send_pdu(sock, pdu)
    print(f"{player_id} → MULLIGAN_CHOICE (keep)")


player1 = connect_player("player_1")
player2 = connect_player("player_2")

send_ready(player1, "player_1")
receive(player1, "player_1")

send_ready(player2, "player_2")
receive(player2, "player_2")

send_mulligan_keep(player1, "player_1")
send_mulligan_keep(player2, "player_2")