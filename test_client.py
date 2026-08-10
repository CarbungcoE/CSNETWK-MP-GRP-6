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


def send_mulligan_keep(sock, player_id, seq_num):
    pdu = {
        "type": "MULLIGAN_CHOICE",
        "seq_num": seq_num,
        "session_id": "test-game",
        "player_id": player_id,
        "keep": True,
        "cards_to_bottom": [],
    }

    send_pdu(sock, pdu)
    print(f"{player_id} → MULLIGAN_CHOICE (seq={seq_num})")


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

print("DEBUG: PLAYER_READY phase complete")
print("DEBUG: about to receive/prepare mulligan state")

# The PLAYER_READY responses were:
# player 1 -> GAME_STATE_UPDATE seq_num=1
# player 2 -> GAME_STATE_UPDATE seq_num=2
#
# The server's GAME_STATE_UPDATE seq_num is the sequence number
# the client should use for its next action.

player1_mulligan_seq = 2
player2_mulligan_seq = 2

print("DEBUG: about to send player_1 mulligan")
send_mulligan_keep(
    player1,
    "player_1",
    player1_mulligan_seq,
)
print("DEBUG: player_1 mulligan sent")

print("DEBUG: about to send player_2 mulligan")
send_mulligan_keep(
    player2,
    "player_2",
    player2_mulligan_seq,
)
print("DEBUG: player_2 mulligan sent")


# P1 may receive a MULLIGAN_RESULT first.
p1_result = receive_until(
    player1,
    "player_1",
    "MULLIGAN_RESULT",
)

if p1_result is None:
    raise RuntimeError(
        "player_1: server closed connection after mulligan"
    )


# P2 may receive its MULLIGAN_RESULT before the MAIN_1 update.
p2_result = receive_until(
    player2,
    "player_2",
    "MULLIGAN_RESULT",
)

if p2_result is None:
    raise RuntimeError(
        "player_2: server closed connection after mulligan"
    )


print("\nBoth players completed mulligan.")

# Now wait for the state that transitions the game into MAIN_1.
main_state = receive_until(
    player2,
    "player_2",
    "GAME_STATE_UPDATE",
)

if main_state is None:
    raise RuntimeError("player_2: server closed connection while waiting for MAIN_1")

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