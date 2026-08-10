import socket
import select

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


def receive_priority_event():
    """Receive the next priority-related PDU from either player socket."""
    readable, _, _ = select.select(
        [player1, player2],
        [],
        [],
        10,
    )

    if not readable:
        raise RuntimeError(
            "Timed out waiting for the next priority event"
        )

    sock = readable[0]
    player_id = "player_1" if sock is player1 else "player_2"
    pdu = receive(sock, player_id)

    if pdu is None:
        raise RuntimeError(
            f"{player_id}: connection closed during priority sequence"
        )

    return sock, player_id, pdu


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
    next_priority = response["player_id"]

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
p1_ready_state = receive(player1, "player_1")

send_ready(player2, "player_2")
p2_ready_state = receive(player2, "player_2")


# ------------------------------------------------------------
# MULLIGAN
# ------------------------------------------------------------

# player_2's PLAYER_READY response already contains the
# MULLIGAN state, so do NOT receive another message from p2.
#
# player_1's PLAYER_READY response was the LOBBY state, so
# player_1 still needs to receive the MULLIGAN state.

if (
    p2_ready_state
    and p2_ready_state.get("type") == "GAME_STATE_UPDATE"
    and p2_ready_state.get("state", {}).get("phase") == "MULLIGAN"
):
    p2_mulligan_state = p2_ready_state
else:
    p2_mulligan_state = receive_until(
        player2,
        "player_2",
        "GAME_STATE_UPDATE",
    )

if (
    p1_ready_state
    and p1_ready_state.get("type") == "GAME_STATE_UPDATE"
    and p1_ready_state.get("state", {}).get("phase") == "MULLIGAN"
):
    p1_mulligan_state = p1_ready_state
else:
    p1_mulligan_state = receive_until(
        player1,
        "player_1",
        "GAME_STATE_UPDATE",
    )

if p1_mulligan_state is None:
    raise RuntimeError(
        "player_1: server closed connection during mulligan"
    )

if p2_mulligan_state is None:
    raise RuntimeError(
        "player_2: server closed connection during mulligan"
    )


p1_mulligan_seq = p1_mulligan_state["seq_num"]
p2_mulligan_seq = p2_mulligan_state["seq_num"]

print(f"player_1 mulligan request seq={p1_mulligan_seq}")
print(f"player_2 mulligan request seq={p2_mulligan_seq}")


send_mulligan_keep(
    player1,
    "player_1",
    p1_mulligan_seq,
)

send_mulligan_keep(
    player2,
    "player_2",
    p2_mulligan_seq,
)


# ------------------------------------------------------------
# MULLIGAN RESULTS
# ------------------------------------------------------------

p1_result = receive_until(
    player1,
    "player_1",
    "MULLIGAN_RESULT",
)

if p1_result is None:
    raise RuntimeError(
        "player_1: server closed connection after mulligan"
    )

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

# ------------------------------------------------------------
# FIRST-TURN PHASES / PRIORITY
# ------------------------------------------------------------

current_state = None
priority_player = None
priority_seq = None

# Priority actions MUST echo the latest PRIORITY_GRANT seq_num.
last_priority_action_sent = 0

while True:
    _, received_player_id, response = receive_priority_event()

    response_type = response.get("type")

    print(
        f"First-turn response on {received_player_id}: "
        f"{response_type} -> {response}"
    )

    if response_type == "GAME_STATE_UPDATE":
        current_state = response.get("state", {})

        phase = current_state.get("phase")
        priority_player = current_state.get("priority_player")

        print(
            f"First-turn state: phase={phase}, "
            f"active={current_state.get('active_player')}, "
            f"priority={priority_player}, "
            f"priority_seq={current_state.get('priority_seq_num')}"
        )

        if phase == "PRECOMBAT_MAIN":
            break

        if priority_player is not None:
            current_priority_seq = current_state.get("priority_seq_num", 0)

            # Both clients receive the same GAME_STATE_UPDATE. Only
            # send one pass for each authoritative priority token.
            if current_priority_seq <= last_priority_action_sent:
                continue

            sock = (
                player1
                if priority_player == "player_1"
                else player2
            )

            send_priority_pass(
                sock,
                priority_player,
                current_priority_seq,
            )

            print(
                f"DEBUG: sent priority pass with "
                f"client seq={server_seq}"
            )

            last_priority_action_sent = current_priority_seq

        continue

    if response_type == "PRIORITY_GRANT":
        priority_player = response.get("player_id")
        server_seq = response.get("seq_num")

        print(
            f"Priority is now {priority_player}; "
            f"server seq={server_seq}; "
            f"client action seq={server_seq}"
        )

        sock = (
            player1
            if priority_player == "player_1"
            else player2
        )

        send_priority_pass(
            sock,
            priority_player,
            server_seq,
        )

        print(
            f"DEBUG: sent priority pass with "
            f"client seq={server_seq}"
        )

        last_priority_action_sent = server_seq
        continue

    if response_type == "ERROR":
        raise RuntimeError(
            f"Unexpected server error during first turn: {response}"
        )

    print(
        f"Ignoring unexpected response during first turn: "
        f"{response}"
    )


print(
    f"\nPRECOMBAT_MAIN reached. "
    f"Priority belongs to {priority_player}."
)

# ------------------------------------------------------------
# Clean shutdown
# ------------------------------------------------------------

player1.close()
player2.close()

print("Connections closed.")