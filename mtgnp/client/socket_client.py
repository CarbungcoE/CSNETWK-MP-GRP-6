import argparse
import socket
import threading
import sys
import time

from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger
from mtgnp.common.pdu import (
    build_player_ready, build_mulligan_choice, build_priority_pass,
    build_play_land, build_cast_spell, build_activate_ability, build_declare_attackers,
    build_declare_blockers, build_assign_damage_order, build_concede, build_discard,
    build_trigger_order_response, build_trigger_choice_response
)
from mtgnp.client.engine import ClientEngine
from mtgnp.client.heartbeat import HeartbeatMonitor

class MTGNPClient:
    def __init__(self, host: str, port: int, player_id: str, verbose: bool):
        self.host = host
        self.port = port
        self.player_id = player_id
        self.logger = VerboseLogger(enabled=verbose, label=f"CLIENT ({player_id})")
        self.sock = None
        self.engine = ClientEngine(player_id)
        self.heartbeat = None
        self.connected = False

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.connected = True
        print(f"Connected to server {self.host}:{self.port}")

        self.heartbeat = HeartbeatMonitor(self.sock)
        self.heartbeat.start()

        threading.Thread(target=self._receive_loop, daemon=True).start()
        self._prompt_loop()

    def _receive_loop(self):
        while self.connected:
            try:
                pdu = recv_pdu(self.sock)
                if not pdu:
                    print("\nServer closed connection.")
                    self.connected = False
                    break
                
                self.logger.log_pdu("S->C", pdu)
                self._handle_pdu(pdu)
            except Exception as e:
                if self.connected:
                    print(f"\nError reading socket: {e}")
                self.connected = False
                break

    def _handle_pdu(self, pdu: dict):
        pdu_type = pdu.get("type")

        if pdu_type == "PONG":
            if self.heartbeat:
                self.heartbeat.receive_pong()
            return

        elif pdu_type == "GAME_STATE_UPDATE":
            self.engine.update_state(pdu)
            self.engine.draw_board()

        elif pdu_type == "PRIORITY_GRANT":
            self.engine.set_priority(pdu)
            if pdu.get("player_id") == self.player_id:
                print(f"\n>>> YOU HAVE PRIORITY (Seq #{self.engine.seq_num}) <<<")
                print("Options: [pass] Pass | [land] Play Land | [cast] Cast Spell | [concede] Concede")

        elif pdu_type == "PHASE_TRANSITION":
            self.engine.seq_num = pdu.get("seq_num", self.engine.seq_num)
            self.engine.phase = pdu.get("to_phase", self.engine.phase)
            print(f"\n*** PHASE TRANSITION: {pdu.get('from_phase')} -> {pdu.get('to_phase')} (Turn {pdu.get('turn')}) ***")

        elif pdu_type == "STACK_PUSH":
            print(f"\n[Stack Push] {pdu.get('item_type')} from {pdu.get('source')} added to stack.")

        elif pdu_type == "STACK_RESOLVE":
            print(f"\n[Stack Resolve] Item {pdu.get('stack_item_id')} resolved as {pdu.get('result')}.")

        elif pdu_type == "COMBAT_DAMAGE_RESULT":
            print("\n*** COMBAT DAMAGE RESOLVED ***")
            for ev in pdu.get("damage_events", []):
                print(f"  {ev.get('source')} dealt {ev.get('amount')} damage to {ev.get('target')}")
            if pdu.get("creatures_died"):
                print(f"  Died: {', '.join(pdu.get('creatures_died'))}")

        elif pdu_type == "TRIGGER_ORDER":
            print(f"\n>>> ORDER YOUR TRIGGERS: {pdu.get('trigger_ids')} <<<")
            t_ids = pdu.get("trigger_ids", [])
            ordered = list(reversed(t_ids))
            resp = build_trigger_order_response(pdu.get("seq_num"), ordered)
            self._send(resp)

        elif pdu_type == "TRIGGER_CHOICE":
            print(f"\n>>> OPTIONAL TRIGGER: {pdu.get('effect_summary')} <<<")
            resp = build_trigger_choice_response(pdu.get("seq_num"), pdu.get("trigger_id"), True)
            self._send(resp)

        elif pdu_type == "ERROR":
            print(f"\n!!! SERVER ERROR [{pdu.get('code')}]: {pdu.get('message')} !!!")

        elif pdu_type == "GAME_OVER":
            self.engine.phase = "LOBBY"
            self.engine.priority_holder = None
            print(f"\n==========================================")
            print(f" GAME OVER! Winner: {pdu.get('winner_id')} | Reason: {pdu.get('reason')}")
            print(f"==========================================")

    def _send(self, pdu: dict):
        try:
            send_pdu(self.sock, pdu)
            self.logger.log_pdu("C->S", pdu)
        except Exception as e:
            print(f"Send failed: {e}")

    def _prompt_loop(self):
        time.sleep(0.5)
        print("\n--- WELCOME TO MTGNP CLIENT ---")
        
        default_deck = [
            "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
            "shock_001", "shock_002", "goblin_guide_001",
            "mountain_001", "mountain_002", "mountain_003"
        ]
        
        ready_pdu = build_player_ready(1, self.player_id, default_deck)
        self._send(ready_pdu)

        while self.connected:
            try:
                cmd = input().strip().lower()
                if not cmd:
                    continue

                if cmd == "pass":
                    self._send(build_priority_pass(self.engine.seq_num))

                elif cmd == "land":
                    card_id = input("Enter land card_id (e.g. mountain_001): ").strip()
                    self._send(build_play_land(self.engine.seq_num, card_id))

                elif cmd == "cast":
                    card_id = input("Enter spell card_id: ").strip()
                    target = input("Enter target (player_1/player_2/creature_id or leave empty): ").strip()
                    targets = [target] if target else []
                    m_color = input("Mana color key (e.g. R/U/B/W/G): ").strip().upper()
                    m_amt = int(input("Mana amount: ").strip() or "1")
                    mana_pay = {m_color: m_amt} if m_color else {"R": 1}
                    self._send(build_cast_spell(self.engine.seq_num, card_id, targets, mana_pay))

                elif cmd == "attack":
                    cid = input("Attacking creature_id: ").strip()
                    target = input("Target player (e.g. player_2): ").strip()
                    atks = [{"creature_id": cid, "target": target}] if cid else []
                    self._send(build_declare_attackers(self.engine.seq_num, atks))

                elif cmd == "block":
                    cid = input("Blocking creature_id: ").strip()
                    target = input("Attacker creature_id to block: ").strip()
                    blks = [{"creature_id": cid, "blocking_id": target}] if cid and target else []
                    self._send(build_declare_blockers(self.engine.seq_num, blks))

                elif cmd == "mulligan":
                    keep = input("Keep hand? (y/n): ").strip().lower() == "y"
                    bottoms = []
                    if keep:
                        b_str = input("Cards to bottom comma-separated (or empty): ").strip()
                        if b_str:
                            bottoms = [x.strip() for x in b_str.split(",")]
                    self._send(build_mulligan_choice(self.engine.seq_num, keep, bottoms))

                elif cmd == "ability":
                    source=input("Source permanent id: ").strip()
                    idx=int(input("Ability index: ").strip() or "0")
                    target=input("Target (optional): ").strip()
                    self._send(build_activate_ability(self.engine.seq_num, source, idx, [target] if target else [], {"tap": True, "mana": {}}))
                elif cmd == "damageorder":
                    aid=input("Attacker id: ").strip()
                    bids=[x.strip() for x in input("Blocker order comma-separated: ").split(",") if x.strip()]
                    self._send(build_assign_damage_order(self.engine.seq_num, aid, bids))
                elif cmd == "discard":
                    ids=[x.strip() for x in input("Cards to discard comma-separated: ").split(",") if x.strip()]
                    self._send(build_discard(self.engine.seq_num, ids))
                elif cmd == "concede":
                    self._send(build_concede(self.engine.seq_num, self.player_id))

                else:
                    print("Unknown command. Valid: pass, land, cast, ability, attack, block, damageorder, discard, mulligan, concede")

            except (KeyboardInterrupt, EOFError):
                print("\nExiting client...")
                self.connected = False
                break

        if self.heartbeat:
            self.heartbeat.stop()
        if self.sock:
            self.sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTGNP Player Client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host IP")
    parser.add_argument("--port", type=int, default=4444, help="Server port")
    parser.add_argument("--id", required=True, help="Unique Player ID")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose PDU logging")

    args = parser.parse_args()
    client = MTGNPClient(host=args.host, port=args.port, player_id=args.id, verbose=args.verbose)
    client.connect()
