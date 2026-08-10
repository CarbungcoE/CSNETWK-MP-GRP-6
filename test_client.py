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

def receive_until(sock, player_id, expected_type):
    while True:
        pdu = receive(sock, player_id)

        if pdu is None:
            raise RuntimeError(
                f"{player_id}: connection closed while waiting for {expected_type}"
            )

        if pdu.get("type") == expected_type:
            return pdu

        print(
            f"{player_id}: ignoring {pdu.get('type')} "
            f"while waiting for {expected_type}"
        )


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


def send_priority_pass(sock, player_id, seq_num):
    pdu = {
        "type": "PRIORITY_PASS",
        "seq_num": seq_num,
        "session_id": "test-game",
        "player_id": player_id,
    }

    send_pdu(sock, pdu)
    print(f"{player_id} → PRIORITY_PASS (seq={seq_num})")


def expect_priority_grant(sock, player_id):
    """
    Receive the server's response to PRIORITY_PASS.

    Returns the seq_num from the PRIORITY_GRANT. That value is
    used as the seq_num of the next PRIORITY_PASS.
    """
    response = receive(sock, player_id)

    if response is None:
        raise RuntimeError(
            f"{player_id}: server closed the connection unexpectedly"
        )

    if response.get("type") != "PRIORITY_GRANT":
        raise RuntimeError(
            f"{player_id}: expected PRIORITY_GRANT, "
            f"got {response}"
        )

    next_seq = response["seq_num"]
    next_priority = response["priority_player"]

    print(
        f"Priority is now {next_priority}; "
        f"next seq_num={next_seq}"
    )

    return next_seq, next_priority


# ------------------------------------------------------------
# Connect both players
# ------------------------------------------------------------

player1 = connect_player("player_1")
player2 = connect_player("player_2")


# ------------------------------------------------------------
# PLAYER_READY
# ------------------------------------------------------------

send_ready(player1, "player_1")
receive(player1, "player_1")

send_ready(player2, "player_2")
receive(player2, "player_2")


# ------------------------------------------------------------
# MULLIGAN
# ------------------------------------------------------------

send_mulligan_keep(player1, "player_1")
send_mulligan_keep(player2, "player_2")


# P1 receives its mulligan result.
receive(player1, "player_1")

# P2 receives the MAIN_1 state.
main_state = receive_until(
    player2,
    "player_2",
    "GAME_STATE_UPDATE",
)

if main_state is None:
    raise RuntimeError("Server closed the connection after mulligan.")

state = main_state.get("state", {})

if state.get("phase") != "MAIN_1":
    raise RuntimeError(
        f"Expected MAIN_1, got {state}"
    )

priority_player = state.get("priority_player")

print(
    f"\nMAIN_1 started. "
    f"Priority belongs to {priority_player}."
)


# ------------------------------------------------------------
# PRIORITY LOOP
# ------------------------------------------------------------
#
# The server owns the sequence/token.
#
# We do NOT assume:
#
#     1 -> 2 -> 3 -> 4
#
# Instead:
#
#     send seq N
#          ↓
#     receive PRIORITY_GRANT seq N+1
#          ↓
#     use that returned seq
# ------------------------------------------------------------

# The first priority action starts with seq_num 1.
priority_seq = 1

# Do several passes so we can verify the token keeps advancing.
for _ in range(4):

    if priority_player == "player_1":
        sock = player1
    else:
        sock = player2

    send_priority_pass(
        sock,
        priority_player,
        priority_seq,
    )

    priority_seq, priority_player = expect_priority_grant(
        sock,
        priority_player,
    )


print("\nPriority test completed successfully.")


# ------------------------------------------------------------
# Clean shutdown
# ------------------------------------------------------------

player1.close()
player2.close()

print("Connections closed.")