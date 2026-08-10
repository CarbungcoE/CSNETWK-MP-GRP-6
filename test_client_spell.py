import select
import socket

from mtgnp.common.framing import send_pdu, recv_pdu

HOST = "127.0.0.1"
PORT = 4444
DECK = [
    "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
    "shock_001", "shock_002", "goblin_guide_001",
    "mountain_001", "mountain_002",
]


def connect(pid):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print(f"{pid} connected")
    return sock


def recv(sock, pid):
    pdu = recv_pdu(sock)
    print(f"{pid} received: {pdu}")
    if pdu is None:
        raise RuntimeError(f"{pid}: server closed connection")
    return pdu


def send(sock, pdu, label):
    send_pdu(sock, pdu)
    print(f"{pdu.get('player_id', '')} → {label} (seq={pdu.get('seq_num')})")


def wait_for(sock, pid, ptype):
    while True:
        pdu = recv(sock, pid)
        if pdu.get("type") == ptype:
            return pdu
        if pdu.get("type") == "ERROR":
            raise RuntimeError(f"{pid}: unexpected ERROR while waiting for {ptype}: {pdu}")


p1 = connect("player_1")
p2 = connect("player_2")
socks = {p1: "player_1", p2: "player_2"}

for sock, pid in ((p1, "player_1"), (p2, "player_2")):
    send(sock, {
        "type": "PLAYER_READY",
        "seq_num": 1,
        "session_id": "test-spell",
        "player_id": pid,
        "deck_list": DECK,
    }, "PLAYER_READY")

p1_state = wait_for(p1, "player_1", "GAME_STATE_UPDATE")
p2_state = wait_for(p2, "player_2", "GAME_STATE_UPDATE")

for sock, pid, state_pdu in ((p1, "player_1", p1_state), (p2, "player_2", p2_state)):
    if state_pdu["state"].get("phase") != "MULLIGAN":
        state_pdu = wait_for(sock, pid, "GAME_STATE_UPDATE")
    send(sock, {
        "type": "MULLIGAN_CHOICE",
        "seq_num": state_pdu["seq_num"],
        "session_id": "test-spell",
        "player_id": pid,
        "keep": True,
        "cards_to_bottom": [],
    }, "MULLIGAN_CHOICE")

wait_for(p1, "player_1", "MULLIGAN_RESULT")
wait_for(p2, "player_2", "MULLIGAN_RESULT")

# Drive the automatic first-turn priority windows until PRECOMBAT_MAIN.
state_by_pid = {}
sent_priority = set()
while True:
    readable, _, _ = select.select([p1, p2], [], [], 10)
    if not readable:
        raise RuntimeError("Timed out waiting for PRECOMBAT_MAIN")
    sock = readable[0]
    pid = socks[sock]
    pdu = recv(sock, pid)
    typ = pdu.get("type")

    if typ == "GAME_STATE_UPDATE":
        state = pdu["state"]
        state_by_pid[pid] = state
        if state.get("phase") == "PRECOMBAT_MAIN":
            active = state["active_player"]
            active_state = state
            break
        holder = state.get("priority_player")
        seq = state.get("priority_seq_num")
        if holder and seq and seq not in sent_priority:
            target = p1 if holder == "player_1" else p2
            send(target, {
                "type": "PRIORITY_PASS",
                "seq_num": seq,
                "session_id": "test-spell",
                "player_id": holder,
            }, "PRIORITY_PASS")
            sent_priority.add(seq)

    elif typ == "PRIORITY_GRANT":
        holder = pdu["player_id"]
        target = p1 if holder == "player_1" else p2
        if pdu["seq_num"] not in sent_priority:
            send(target, {
                "type": "PRIORITY_PASS",
                "seq_num": pdu["seq_num"],
                "session_id": "test-spell",
                "player_id": holder,
            }, "PRIORITY_PASS")
            sent_priority.add(pdu["seq_num"])

active_sock = p1 if active == "player_1" else p2
opponent = "player_2" if active == "player_1" else "player_1"
hand = active_state["hand"]
lands = [c for c in hand if c.rsplit("_", 1)[0] == "mountain"]
if not lands:
    raise RuntimeError(f"Active player has no Mountain in hand: {hand}")
land = lands[0]

send(active_sock, {
    "type": "PLAY_LAND",
    "seq_num": active_state["priority_seq_num"],
    "session_id": "test-spell",
    "player_id": active,
    "card_id": land,
}, "PLAY_LAND")

# Collect the state update and fresh priority grant after the land play.
land_state = None
land_grant = None
while land_state is None or land_grant is None:
    readable, _, _ = select.select([p1, p2], [], [], 10)
    if not readable:
        raise RuntimeError("Timed out after PLAY_LAND")
    sock = readable[0]
    pid = socks[sock]
    pdu = recv(sock, pid)
    if pdu.get("type") == "GAME_STATE_UPDATE" and pdu["state"].get("active_player") == active:
        land_state = pdu["state"]
    elif pdu.get("type") == "PRIORITY_GRANT" and pdu.get("player_id") == active:
        land_grant = pdu
    elif pdu.get("type") == "ERROR":
        raise RuntimeError(f"PLAY_LAND failed: {pdu}")

if not any(c.get("id") == land and not c.get("tapped") for c in land_state["battlefield"][active]):
    raise RuntimeError(f"Mountain was not placed untapped: {land_state['battlefield'][active]}")

spells = [c for c in land_state["hand"] if c.rsplit("_", 1)[0] in {"shock", "lightning_bolt"}]
if not spells:
    raise RuntimeError(f"No test damage spell in active hand: {land_state['hand']}")
spell = spells[0]
expected_damage = 2 if spell.rsplit("_", 1)[0] == "shock" else 3

send(active_sock, {
    "type": "CAST_SPELL",
    "seq_num": land_grant["seq_num"],
    "session_id": "test-spell",
    "player_id": active,
    "card_id": spell,
    "targets": [opponent],
    "mana_payment": {"R": 1},
}, "CAST_SPELL")

stack_push_seen = False
cast_grant = None
while not stack_push_seen or cast_grant is None:
    readable, _, _ = select.select([p1, p2], [], [], 10)
    if not readable:
        raise RuntimeError("Timed out after CAST_SPELL")
    sock = readable[0]
    pid = socks[sock]
    pdu = recv(sock, pid)
    if pdu.get("type") == "STACK_PUSH":
        stack_push_seen = True
        if pdu.get("source") != spell:
            raise RuntimeError(f"Unexpected stack source: {pdu}")
    elif pdu.get("type") == "PRIORITY_GRANT":
        cast_grant = pdu
    elif pdu.get("type") == "ERROR":
        raise RuntimeError(f"CAST_SPELL failed: {pdu}")

if cast_grant.get("player_id") != active:
    raise RuntimeError(f"Caster did not retain priority: {cast_grant}")

# Active player passes, then opponent passes; the spell must resolve.
send(active_sock, {
    "type": "PRIORITY_PASS",
    "seq_num": cast_grant["seq_num"],
    "session_id": "test-spell",
    "player_id": active,
}, "PRIORITY_PASS")

opponent_sock = p2 if opponent == "player_2" else p1
opponent_grant = wait_for(opponent_sock, opponent, "PRIORITY_GRANT")
send(opponent_sock, {
    "type": "PRIORITY_PASS",
    "seq_num": opponent_grant["seq_num"],
    "session_id": "test-spell",
    "player_id": opponent,
}, "PRIORITY_PASS")

resolved = False
updated_life = None
while not resolved or updated_life is None:
    readable, _, _ = select.select([p1, p2], [], [], 10)
    if not readable:
        raise RuntimeError("Timed out waiting for spell resolution")
    sock = readable[0]
    pid = socks[sock]
    pdu = recv(sock, pid)
    if pdu.get("type") == "STACK_RESOLVE":
        resolved = True
        if pdu.get("result") != "RESOLVED":
            raise RuntimeError(f"Spell did not resolve: {pdu}")
    elif pdu.get("type") == "GAME_STATE_UPDATE":
        life = pdu["state"]["life_totals"][opponent]
        if life == 20 - expected_damage:
            updated_life = life
    elif pdu.get("type") == "PRIORITY_GRANT":
        pass
    elif pdu.get("type") == "ERROR":
        raise RuntimeError(f"Unexpected resolution ERROR: {pdu}")

print(f"\nSPELL milestone passed: {spell} resolved for {expected_damage} damage.")
print(f"{opponent} life total: {updated_life}")

p1.close()
p2.close()
