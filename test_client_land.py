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


def receive(sock, player_id):
    pdu = recv_pdu(sock)
    print(f"\n{player_id} received:")
    print(pdu)
    return pdu


def receive_until(sock, player_id, expected_type):
    while True:
        pdu = receive(sock, player_id)
        if pdu is None:
            raise RuntimeError(f"{player_id}: connection closed waiting for {expected_type}")
        if pdu.get("type") == expected_type:
            return pdu


def send_ready(sock, player_id):
    send_pdu(sock, {
        "type": "PLAYER_READY",
        "seq_num": 1,
        "session_id": "test-game",
        "player_id": player_id,
        "deck_list": [
            "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
            "shock_001", "shock_002", "goblin_guide_001",
            "mountain_001", "mountain_002",
        ],
    })


def send_mulligan_keep(sock, player_id, seq_num):
    send_pdu(sock, {
        "type": "MULLIGAN_CHOICE",
        "seq_num": seq_num,
        "session_id": "test-game",
        "player_id": player_id,
        "keep": True,
        "cards_to_bottom": [],
    })


def send_priority_pass(sock, player_id, seq_num):
    send_pdu(sock, {
        "type": "PRIORITY_PASS",
        "seq_num": seq_num,
        "session_id": "test-game",
        "player_id": player_id,
    })
    print(f"{player_id} → PRIORITY_PASS (seq={seq_num})")


def send_play_land(sock, player_id, seq_num, card_id):
    send_pdu(sock, {
        "type": "PLAY_LAND",
        "seq_num": seq_num,
        "session_id": "test-game",
        "player_id": player_id,
        "card_id": card_id,
    })
    print(f"{player_id} → PLAY_LAND {card_id} (seq={seq_num})")


player1 = connect_player("player_1")
player2 = connect_player("player_2")

send_ready(player1, "player_1")
p1_ready = receive(player1, "player_1")
send_ready(player2, "player_2")
p2_ready = receive(player2, "player_2")

p1_mulligan = p1_ready if p1_ready.get("state", {}).get("phase") == "MULLIGAN" else receive_until(player1, "player_1", "GAME_STATE_UPDATE")
p2_mulligan = p2_ready if p2_ready.get("state", {}).get("phase") == "MULLIGAN" else receive_until(player2, "player_2", "GAME_STATE_UPDATE")

send_mulligan_keep(player1, "player_1", p1_mulligan["seq_num"])
send_mulligan_keep(player2, "player_2", p2_mulligan["seq_num"])

receive_until(player1, "player_1", "MULLIGAN_RESULT")
receive_until(player2, "player_2", "MULLIGAN_RESULT")

socks = {player1: "player_1", player2: "player_2"}
last_sent_seq = 0
current_state = None
priority_player = None
priority_seq = None

# Drive automatic priority windows until PRECOMBAT_MAIN.
while True:
    readable, _, _ = select.select([player1, player2], [], [], 10)
    if not readable:
        raise RuntimeError("Timed out waiting for first-turn progression")

    sock = readable[0]
    pid = socks[sock]
    pdu = receive(sock, pid)
    ptype = pdu.get("type")

    if ptype == "GAME_STATE_UPDATE":
        current_state = pdu["state"]
        phase = current_state["phase"]
        priority_player = current_state.get("priority_player")
        priority_seq = current_state.get("priority_seq_num")
        print(f"STATE: phase={phase}, priority={priority_player}, seq={priority_seq}")

        if phase == "PRECOMBAT_MAIN":
            break

        if priority_player and priority_seq and priority_seq > last_sent_seq:
            target = player1 if priority_player == "player_1" else player2
            send_priority_pass(target, priority_player, priority_seq)
            last_sent_seq = priority_seq

    elif ptype == "PRIORITY_GRANT":
        priority_player = pdu["priority_player"]
        priority_seq = pdu["seq_num"]
        target = player1 if priority_player == "player_1" else player2
        send_priority_pass(target, priority_player, priority_seq)
        last_sent_seq = priority_seq

    elif ptype == "ERROR":
        raise RuntimeError(f"Unexpected first-turn error: {pdu}")

active = current_state["active_player"]
hand = current_state["hand"]
lands = [c for c in hand if c.rsplit("_", 1)[0] in {"mountain", "forest", "plains", "island", "swamp"}]
if not lands:
    raise RuntimeError(f"No land in active player's hand: {hand}")

card_id = lands[0]
active_sock = player1 if active == "player_1" else player2
send_play_land(active_sock, active, current_state["priority_seq_num"], card_id)

# The server should broadcast a state update to both players, then grant
# fresh priority to the active player.
seen_state = {}
grant = None
for _ in range(4):
    readable, _, _ = select.select([player1, player2], [], [], 10)
    if not readable:
        raise RuntimeError("Timed out waiting for land-play response")
    sock = readable[0]
    pid = socks[sock]
    pdu = receive(sock, pid)

    if pdu.get("type") == "GAME_STATE_UPDATE":
        seen_state[pid] = pdu["state"]
    elif pdu.get("type") == "PRIORITY_GRANT":
        grant = pdu
        break
    elif pdu.get("type") == "ERROR":
        raise RuntimeError(f"PLAY_LAND rejected: {pdu}")

if not grant:
    raise RuntimeError("Expected PRIORITY_GRANT after PLAY_LAND")

state = seen_state.get(active)
if state is None:
    raise RuntimeError("Active player did not receive land-play state update")

battlefield = state["battlefield"][active]
if not any(item.get("id") == card_id for item in battlefield):
    raise RuntimeError(f"{card_id} missing from battlefield: {battlefield}")
if card_id in state["hand"]:
    raise RuntimeError(f"{card_id} still present in hand: {state['hand']}")
if not state.get("land_played_this_turn"):
    raise RuntimeError("land_played_this_turn was not set")
if grant.get("priority_player") != active:
    raise RuntimeError(f"Priority was not retained by active player: {grant}")

print(f"\nPLAY_LAND milestone passed: {active} played {card_id}.")
print(f"Fresh priority token: {grant['seq_num']}")

player1.close()
player2.close()
