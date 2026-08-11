import argparse
import queue
import socket
import threading
import time

from mtgnp.common.framing import send_pdu, recv_pdu
from mtgnp.common.logger import VerboseLogger
from mtgnp.common.pdu import (
    build_player_ready, build_mulligan_choice, build_priority_pass,
    build_play_land, build_cast_spell, build_activate_ability, build_declare_attackers,
    build_declare_blockers, build_assign_damage_order, build_concede, build_discard,
    build_trigger_order_response, build_trigger_choice_response,
)
from mtgnp.client.engine import ClientEngine
from mtgnp.client.heartbeat import HeartbeatMonitor
from mtgnp.game.card_catalog import CardCatalog


class MTGNPClient:
    """Interactive MTGNP client with state-aware, protocol-friendly prompts."""

    MAIN_PHASES = {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}
    SPELL_MAIN_ONLY = {"Sorcery", "Creature", "Artifact Creature", "Artifact", "Enchantment"}

    def __init__(self, host: str, port: int, player_id: str, verbose: bool, session_id: str = "test-game"):
        self.host = host
        self.port = port
        self.player_id = player_id
        self.session_id = session_id
        self.logger = VerboseLogger(enabled=verbose, label=f"CLIENT ({player_id})")
        self.sock = None
        self._send_lock = threading.Lock()
        self._output_lock = threading.Lock()
        self._deferred_output = []
        self.engine = ClientEngine(player_id)
        self.heartbeat = None
        self.connected = False
        self._heartbeat_started = False

        self.card_catalog = CardCatalog()
        self.input_queue: queue.Queue[str] = queue.Queue()
        self.input_thread = None
        self.input_context = None
        self.pending_interaction = None
        self.phase_action_seq = 0
        self.cleanup_action_seq = None
        # Local UX state for the London mulligan flow. The server is
        # authoritative; these fields mirror the latest GAME_STATE_UPDATE.
        self.mulligan_count = 0
        self.mulligan_waiting_for_state = False
        self.running = False
        self._command_prompt_shown = False
        self._waiting_for_server_input = False

    # ------------------------------------------------------------------
    # Connection / transport
    # ------------------------------------------------------------------

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.connected = True
        self.running = True
        print(f"Connected to server {self.host}:{self.port}")

        self.heartbeat = HeartbeatMonitor(
            self.sock,
            send_callback=self._send_heartbeat_pdu,
            verbose=self.logger.enabled,
        )

        threading.Thread(target=self._receive_loop, daemon=True).start()
        self.input_thread = threading.Thread(target=self._stdin_loop, daemon=True)
        self.input_thread.start()
        self._prompt_loop()

    def _stdin_loop(self):
        # Keep stdin collection independent from the protocol receive thread.
        # Do not print a generic "Command:" prompt here: interactive protocol
        # flows (mulligan, targets, blockers, etc.) provide their own prompts.
        # Printing from this thread used to create confusing duplicate prompts
        # and allowed stale-looking input to appear while a sub-prompt was active.
        while self.running:
            try:
                line = input()
            except (KeyboardInterrupt, EOFError):
                self.input_queue.put("__EXIT__")
                return
            self.input_queue.put(line)

    def _receive_loop(self):
        while self.connected:
            try:
                pdu = recv_pdu(self.sock)
                if not pdu:
                    self._print_line("\nServer closed connection.")
                    self.connected = False
                    break
                self.logger.log_pdu("S->C", pdu)
                self._handle_pdu(pdu)
            except Exception as e:
                if self.connected:
                    self._print_line(f"\nError reading socket: {e}")
                self.connected = False
                break

    # ------------------------------------------------------------------
    # Terminal UX helpers
    # ------------------------------------------------------------------

    def _interaction_active(self):
        return self.input_context is not None or self.pending_interaction is not None

    def _print_line(self, text="", *, defer_if_interacting=True):
        """Print without letting unsolicited network updates clobber an active prompt.

        The receive thread runs independently from stdin.  While the user is answering
        a multi-step prompt (mulligan, land, cast, target, etc.), queue background
        server notifications and flush them after that interaction completes.
        """
        if defer_if_interacting and self._interaction_active():
            self._deferred_output.append(text)
            return
        with self._output_lock:
            print(text)

    def _print_multiline(self, text, *, defer_if_interacting=True):
        if defer_if_interacting and self._interaction_active():
            self._deferred_output.extend(text.splitlines())
            return
        with self._output_lock:
            print(text)

    def _flush_deferred_output(self):
        if not self._deferred_output or self._interaction_active():
            return
        pending = self._deferred_output
        self._deferred_output = []
        with self._output_lock:
            print("\n--- Updates received while you were answering ---")
            for line in pending:
                print(line)
            print("--- End deferred updates ---")

    # ------------------------------------------------------------------
    # Server messages
    # ------------------------------------------------------------------

    def _handle_pdu(self, pdu: dict):
        pdu_type = pdu.get("type")

        if pdu_type == "PONG":
            if self.heartbeat:
                self.heartbeat.receive_pong(int(pdu.get("seq_num", 0)))
            if self.logger.enabled:
                self._print_line("[heartbeat] PONG")
            return

        if pdu_type == "GAME_STATE_UPDATE":
            previous_phase = self.engine.phase
            was_interacting = self._interaction_active()
            self.engine.update_state(pdu)
            self._update_action_tokens(pdu)

            # _waiting_for_server_input is currently a mulligan-only guard.
            # Once the authoritative state leaves MULLIGAN, never let that
            # guard leak into normal gameplay. Without this reset, a player
            # who kept their opening hand can reach UPKEEP/MAIN with the
            # flag still set and every subsequent command is rejected as if
            # the previous mulligan were still processing.
            if self.engine.phase != "MULLIGAN":
                self._waiting_for_server_input = False
                self.mulligan_waiting_for_state = False

            if not self._interaction_active():
                self._command_prompt_shown = False

            # Mulligan is an interactive sub-flow. Handle its prompts before
            # printing the generic action list so the user never sees
            # "mulligan" offered while they are already answering a
            # mulligan question.
            # Mulligan state is authoritative in every GAME_STATE_UPDATE.
            # A rejected hand produces a fresh hand and another keep decision;
            # a kept hand must become a waiting state rather than continuing
            # to offer the mulligan command.
            if self.engine.phase == "MULLIGAN":
                self.mulligan_count = self.engine.mulligan_count
                if previous_phase != "MULLIGAN":
                    self.mulligan_waiting_for_state = False

                if (
                    not self.engine.mulligan_kept
                    and self.mulligan_waiting_for_state
                    and self.input_context is None
                ):
                    self.mulligan_waiting_for_state = False
                    self._waiting_for_server_input = False
                    self.input_context = {"kind": "mulligan_keep"}
                    print("\nNew hand dealt.")
                    print(
                        f"You have mulliganed {self.mulligan_count} "
                        f"time{"s" if self.mulligan_count != 1 else ""}."
                    )
                    print("Keep this new hand? (y/n):")
                elif self.engine.mulligan_kept and self.input_context is not None:
                    self.input_context = None
                    print("\nYour hand is kept. Waiting for the other player...")

            # Never redraw the entire board or generic action list over an active
            # local prompt.  The state above is still updated silently, so the next
            # interaction uses authoritative server state.
            local_prompt_started = self._interaction_active() and not was_interacting
            if not was_interacting or local_prompt_started:
                self.engine.draw_board()
                self._print_available_actions()

            # Do not start the heartbeat until the server has answered the
            # initial PLAYER_READY handshake.  Starting the heartbeat from
            # _prompt_loop immediately after PLAYER_READY creates an avoidable
            # startup race: PING can be written while the client/server are
            # still completing the initial lobby state exchange.
            if (
                self.heartbeat is not None
                and self.running
                and not self._heartbeat_started
            ):
                self._heartbeat_started = True
                self.heartbeat.start()
                if self.logger.enabled:
                    print("[heartbeat] monitor started after initial server state")
            return

        if pdu_type == "PRIORITY_GRANT":
            self.engine.set_priority(pdu)
            if pdu.get("player_id") == self.player_id:
                # A local priority grant is an actionable event and should always
                # surface, even if a previous prompt just completed.
                self._print_line(f"\n>>> YOU HAVE PRIORITY (Seq #{self.engine.seq_num}) <<<")
                if not self._interaction_active():
                    self._print_available_actions()
            elif not self._interaction_active():
                self._print_line(f"\nPriority passed to {pdu.get('player_id')}")
            return

        if pdu_type == "PHASE_TRANSITION":
            # PHASE_TRANSITION.seq_num is a server transport/event sequence.
            # It is NOT the priority action token, so do not overwrite
            # engine.seq_num here. The following GAME_STATE_UPDATE carries
            # the authoritative priority_seq_num.
            self.engine.server_seq_num = int(pdu.get("seq_num", self.engine.server_seq_num))
            self.engine.phase = pdu.get("to_phase", self.engine.phase)
            self.phase_action_seq = self.engine.server_seq_num
            message = (
                f"*** PHASE TRANSITION: {pdu.get('from_phase')} -> "
                f"{pdu.get('to_phase')} (Turn {pdu.get('turn')}) ***"
            )
            self._print_line("\n" + message)
            if not self._interaction_active():
                self._print_available_actions()
            return

        if pdu_type == "STACK_PUSH":
            self._print_line(f"\n[Stack Push] {pdu.get('item_type')} from {pdu.get('source')} added to stack.")
            return

        if pdu_type == "STACK_RESOLVE":
            self._print_line(f"\n[Stack Resolve] Item {pdu.get('stack_item_id')} resolved as {pdu.get('result')}.")
            return

        if pdu_type == "COMBAT_DAMAGE_RESULT":
            lines = ["\n*** COMBAT DAMAGE RESOLVED ***"]
            lines.extend(
                f"  {ev.get('source')} dealt {ev.get('amount')} damage to {ev.get('target')}"
                for ev in pdu.get("damage_events", [])
            )
            if pdu.get("creatures_died"):
                lines.append(f"  Died: {', '.join(pdu.get('creatures_died'))}")
            self._print_multiline("\n".join(lines))
            return

        if pdu_type == "TRIGGER_ORDER":
            if pdu.get("player_id") != self.player_id:
                return
            ids = list(pdu.get("trigger_ids", []))
            self.pending_interaction = {
                "kind": "trigger_order",
                "seq": pdu.get("seq_num", self.engine.seq_num),
                "trigger_ids": ids,
            }
            print("\n>>> TRIGGER ORDER REQUIRED <<<")
            for i, tid in enumerate(ids):
                print(f"  [{i}] {tid}")
            print("Enter trigger indexes in the desired order, comma-separated.")
            return

        if pdu_type == "TRIGGER_CHOICE":
            self.pending_interaction = {
                "kind": "trigger_choice",
                "seq": pdu.get("seq_num", self.engine.seq_num),
                "trigger_id": pdu.get("trigger_id"),
                "effect_summary": pdu.get("effect_summary", ""),
                "requires_target": bool(pdu.get("requires_target")),
                "legal_targets": list(pdu.get("legal_targets", [])),
            }
            print("\n>>> OPTIONAL TRIGGER <<<")
            print(f"Trigger: {pdu.get('trigger_id')}")
            print(f"Effect: {pdu.get('effect_summary', 'No summary provided')}")
            print("Accept trigger? (y/n)")
            return

        if pdu_type == "MULLIGAN_RESULT":
            kept = bool(pdu.get("kept"))
            if kept:
                # The mulligan action has completed. Do not carry the
                # mulligan-only server-wait guard into the actual game.
                # Otherwise every later command (pass/cast/land/etc.) is
                # rejected with the misleading "previous action" message.
                self._waiting_for_server_input = False
                self.mulligan_waiting_for_state = False
                self.engine.mulligan_kept = True
                self.input_context = None
                self._print_line("\nHand kept.")
                if self.mulligan_count:
                    self._print_line(
                        f"Because you mulliganed {self.mulligan_count} time"
                        f"{"s" if self.mulligan_count != 1 else ""}, "
                        f"you must put {self.mulligan_count} card"
                        f"{"s" if self.mulligan_count != 1 else ""} on the bottom of your library."
                    )
                self._print_line("Waiting for the other player...")
            else:
                self.mulligan_waiting_for_state = True
                self._print_line("\nMulligan accepted.")
                self._print_line("Your current hand is being replaced with a new 7-card hand...")
            return

        if pdu_type == "ERROR":
            self._print_line(f"\n!!! SERVER ERROR [{pdu.get('code')}]: {pdu.get('message')} !!!")
            return

        if pdu_type == "GAME_OVER":
            self.engine.phase = "LOBBY"
            self.engine.priority_holder = None
            print("\n==========================================")
            print(f" GAME OVER! Winner: {pdu.get('winner_id')} | Reason: {pdu.get('reason')}")
            print("==========================================")
            return

    def _update_action_tokens(self, pdu):
        state = pdu.get("state", {})
        self.phase_action_seq = pdu.get("seq_num", self.phase_action_seq)
        if state.get("phase") == "CLEANUP" and len(self.engine.hand) > 7:
            self.cleanup_action_seq = pdu.get("seq_num")
        else:
            self.cleanup_action_seq = None

    # ------------------------------------------------------------------
    # State-aware UX
    # ------------------------------------------------------------------

    def _available_commands(self):
        if not self.connected or self.engine.phase == "LOBBY":
            return []

        phase = self.engine.phase
        commands = []

        if phase == "MULLIGAN":
            # Wait for the authoritative server response after submitting a
            # mulligan decision; do not briefly expose a generic command prompt.
            if self.mulligan_waiting_for_state:
                return []
            if self.engine.mulligan_kept or self.input_context is not None:
                return ["concede"] if self.engine.mulligan_kept else []
            return ["mulligan", "concede"]

        if phase == "CLEANUP" and self.cleanup_action_seq is not None:
            return ["discard", "concede"]

        if phase == "DECLARE_ATTACKERS" and self.engine.active_player == self.player_id:
            return ["attack", "concede"]

        if phase == "DECLARE_BLOCKERS" and self.engine.active_player != self.player_id:
            return ["block", "concede"]

        if phase == "ASSIGN_DAMAGE_ORDER" and self.engine.active_player == self.player_id:
            return ["damageorder", "concede"]

        if self.engine.priority_holder == self.player_id:
            commands.append("pass")
            commands.append("concede")

            if phase in self.MAIN_PHASES and self.engine.active_player == self.player_id:
                if not self.engine.land_played and self._land_cards():
                    commands.append("land")

            if self._castable_cards():
                commands.append("cast")

            if self._activatable_permanents():
                commands.append("ability")

        elif self.engine.priority_holder:
            commands.append("concede")

        return commands

    def _print_available_actions(self):
        commands = self._available_commands()
        if not commands:
            return
        print("\nAvailable actions: " + " | ".join(commands))

    def _land_cards(self):
        return [cid for cid in self.engine.hand if self._card(cid).get("Card Type") == "Land"]

    def _castable_cards(self):
        result = []
        for cid in self.engine.hand:
            card = self._card(cid)
            ctype = card.get("Card Type")
            if not ctype or ctype == "Land":
                continue
            if ctype in self.SPELL_MAIN_ONLY:
                if self.engine.phase in self.MAIN_PHASES and self.engine.active_player == self.player_id:
                    result.append(cid)
            else:
                result.append(cid)
        return result

    def _activatable_permanents(self):
        return [c for c in self.engine.battlefield.get(self.player_id, []) if self._card(c.get("id"))]

    def _card(self, card_id):
        return self.card_catalog.get_by_instance_id(card_id) or {}

    def _show_card_choices(self, cards, title):
        print(f"\n{title}")
        for i, cid in enumerate(cards):
            card = self._card(cid)
            name = card.get("Card Name", cid)
            ctype = card.get("Card Type", "?")
            effect = card.get("Simplified Effect", "")
            print(f"  [{i}] {cid} — {name} ({ctype})")
            if effect:
                print(f"      {effect}")

    def _choose_from(self, value, options):
        value = value.strip()
        if value.isdigit():
            idx = int(value)
            if 0 <= idx < len(options):
                return options[idx]
            return None
        return value if value in options else None

    def _legal_target_choices(self, effect: str):
        effect = effect.lower()
        choices = []
        wants_player = "any target" in effect or "target player" in effect
        wants_creature = "any target" in effect or "target creature" in effect
        wants_permanent = "target permanent" in effect
        wants_spell = "target spell" in effect
        wants_artifact = "target artifact" in effect
        wants_enchantment = "target enchantment" in effect
        wants_noncreature = "target noncreature" in effect

        if wants_player:
            choices.extend(self.engine.life_totals.keys())

        if wants_creature or wants_permanent or wants_artifact or wants_enchantment or wants_noncreature:
            for perms in self.engine.battlefield.values():
                for perm in perms:
                    cid = perm.get("id")
                    if not cid:
                        continue
                    card = self._card(cid)
                    ctype = card.get("Card Type", "")
                    color = card.get("Color", "")
                    is_creature = "Creature" in ctype
                    is_artifact = ctype.startswith("Artifact")
                    is_enchantment = ctype == "Enchantment"
                    if wants_creature and not is_creature and not wants_permanent and not wants_artifact and not wants_enchantment and not wants_noncreature:
                        continue
                    if wants_artifact and not is_artifact:
                        continue
                    if wants_enchantment and not is_enchantment:
                        continue
                    if wants_noncreature and is_creature:
                        continue
                    if wants_creature and not is_creature and not wants_permanent and not wants_artifact and not wants_enchantment and not wants_noncreature:
                        continue
                    if "nonblack" in effect and color == "B":
                        continue
                    if "nonartifact" in effect and is_artifact:
                        continue
                    choices.append(cid)

        if wants_spell:
            choices.extend(item.get("stack_item_id") for item in self.engine.stack if item.get("stack_item_id"))

        return [x for x in dict.fromkeys(choices) if x]

    # ------------------------------------------------------------------
    # Input state machine
    # ------------------------------------------------------------------

    def _prompt_loop(self):
        time.sleep(0.5)
        print("\n--- WELCOME TO MTGNP CLIENT ---")

        default_deck = [
            "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
            "shock_001", "shock_002", "goblin_guide_001",
            "mountain_001", "mountain_002",
        ]
        ready_pdu = build_player_ready(1, self.player_id, default_deck)
        ready_pdu["session_id"] = self.session_id
        self._send(ready_pdu)

        while self.running:
            # Print the generic command prompt exactly once when a local
            # action is available. The previous implementation printed it
            # every 200 ms while waiting for stdin, producing repeated
            # "Command:" text and making interactive prompts unreadable.
            if (
                not self._interaction_active()
                and self._available_commands()
                and not self._command_prompt_shown
            ):
                print("Command: ", end="", flush=True)
                self._command_prompt_shown = True
            try:
                line = self.input_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if line == "__EXIT__":
                self.running = False
                self.connected = False
                break

            self._process_input(line.strip())

        if self.heartbeat:
            self.heartbeat.stop()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _process_input(self, raw):
        text = raw.strip()

        # Empty input is meaningful while an interactive prompt is active.
        # In particular, Enter at a mana-payment prompt means use the card's
        # required/default colors. Optional selection prompts may also use
        # Enter to mean "choose none".
        if not text and not self.input_context and not self.pending_interaction:
            return

        self._command_prompt_shown = False

        if self._waiting_for_server_input and not self._interaction_active():
            print("Server is processing your previous action; please wait for the next prompt.")
            return

        if self.pending_interaction:
            if self._process_pending_interaction(text):
                self._flush_deferred_output()
                return

        if self.input_context:
            self._process_context(text)
            self._flush_deferred_output()
            return

        cmd = text.lower()
        available = self._available_commands()
        if cmd not in available:
            print(f"Command '{cmd}' is not available right now.")
            if available:
                print("Available: " + " | ".join(available))
            else:
                print("No player action is currently available; wait for the server.")
            return

        if cmd == "pass":
            self._send(build_priority_pass(self.engine.seq_num))
        elif cmd == "concede":
            self._send(build_concede(self.engine.seq_num, self.player_id))
        elif cmd == "mulligan":
            self.input_context = {"kind": "mulligan_confirm"}
            print("\nMULLIGAN: your entire current hand will be replaced with a new 7-card hand.")
            print("You will then decide whether to keep the new hand.")
            print("Mulligan this hand? (y/n):")
        elif cmd == "land":
            cards = self._land_cards()
            self._show_card_choices(cards, "Choose a land to play (index or card id):")
            self.input_context = {"kind": "land", "cards": cards}
        elif cmd == "cast":
            cards = self._castable_cards()
            self._show_card_choices(cards, "Choose a spell to cast (index or card id):")
            self.input_context = {"kind": "cast_card", "cards": cards}
        elif cmd == "ability":
            permanents = self._activatable_permanents()
            print("\nChoose a permanent:")
            for i, perm in enumerate(permanents):
                cid = perm.get("id")
                card = self._card(cid)
                print(f"  [{i}] {cid} — {card.get('Card Name', cid)}")
            self.input_context = {"kind": "ability_source", "permanents": permanents}
        elif cmd == "attack":
            creatures = [c for c in self.engine.battlefield.get(self.player_id, []) if "power" in c or "Power" in self._card(c.get("id"))]
            print("\nChoose attackers by indexes, comma-separated (or empty for no attackers):")
            for i, c in enumerate(creatures):
                print(f"  [{i}] {c.get('id')}")
            self.input_context = {"kind": "attackers", "creatures": creatures}
        elif cmd == "block":
            creatures = [c for c in self.engine.battlefield.get(self.player_id, []) if "power" in c or "Power" in self._card(c.get("id"))]
            print("\nChoose blocking creature index (or empty for none):")
            for i, c in enumerate(creatures):
                print(f"  [{i}] {c.get('id')}")
            self.input_context = {"kind": "blocker_source", "creatures": creatures}
        elif cmd == "damageorder":
            print("Attacker id:")
            self.input_context = {"kind": "damage_attacker"}
        elif cmd == "discard":
            count = max(0, len(self.engine.hand) - 7)
            self._show_card_choices(self.engine.hand, f"Choose {count} card(s) to discard by indexes, comma-separated:")
            self.input_context = {"kind": "discard", "cards": list(self.engine.hand), "count": count}

        self._flush_deferred_output()

    def _process_pending_interaction(self, text):
        p = self.pending_interaction
        if p["kind"] == "trigger_order":
            indexes = [x.strip() for x in text.split(",") if x.strip()]
            try:
                ordered = [p["trigger_ids"][int(i)] for i in indexes]
            except (ValueError, IndexError):
                ordered = []
            if len(ordered) != len(p["trigger_ids"]) or set(ordered) != set(p["trigger_ids"]):
                print("Invalid order. Enter every trigger index exactly once, comma-separated.")
                return True
            self._send(build_trigger_order_response(p["seq"], ordered))
            self.pending_interaction = None
            return True

        if p["kind"] == "trigger_choice" and p.get("stage") == "target":
            targets = p["legal_targets"]
            target = self._choose_from(text, targets)
            if target is None:
                print("Invalid target.")
                return True
            self._send(build_trigger_choice_response(p["seq"], p["trigger_id"], True, target))
            self.pending_interaction = None
            return True

        if p["kind"] == "trigger_choice":
            answer = text.lower()
            if answer not in {"y", "n", "yes", "no"}:
                print("Enter y or n.")
                return True
            accept = answer in {"y", "yes"}
            if accept and p["requires_target"]:
                targets = p["legal_targets"]
                if not targets:
                    print("This trigger requires a target, but the server supplied no legal targets.")
                    return True
                print("Choose a target:")
                for i, target in enumerate(targets):
                    print(f"  [{i}] {target}")
                p["stage"] = "target"
                self.pending_interaction = p
                return True
            self._send(build_trigger_choice_response(p["seq"], p["trigger_id"], accept))
            self.pending_interaction = None
            return True

        return False

    def _prompt_mulligan_bottom(self):
        self.mulligan_count = self.engine.mulligan_count
        hand_size = len(self.engine.hand)

        if self.mulligan_count == 0:
            print("\nNo cards need to be put on the bottom because this is your original hand.")
            self._send(build_mulligan_choice(self.engine.seq_num, True, []))
            self.input_context = None
            return

        # MTGNP permits unlimited mulligans, but its RFC also requires
        # exactly N bottomed cards after N mulligans. A redraw is seven cards,
        # so once N exceeds the current hand size, keeping is impossible.
        # Do not present an impossible card-selection prompt; let the player
        # mulligan again instead.
        if self.mulligan_count > hand_size:
            print(
                f"\nYou have mulliganed {self.mulligan_count} "
                f"time{"s" if self.mulligan_count != 1 else ""}, "
                f"but your current hand contains only {hand_size} card"
                f"{"s" if hand_size != 1 else ""}."
            )
            print(
                "MTGNP requires exactly N cards to be bottomed when you keep. "
                "There are not enough cards in this hand to satisfy that rule."
            )
            print(
                "You cannot keep this hand; mulligan again if you want to continue."
            )
            self.input_context = None
            return

        print(
            f"\nKeep this hand. Because you mulliganed {self.mulligan_count} "
            f"time{"s" if self.mulligan_count != 1 else ""}, "
            f"choose exactly {self.mulligan_count} card"
            f"{"s" if self.mulligan_count != 1 else ""} to put on the bottom of your library."
        )
        print("Choose card indexes, comma-separated:")
        for i, cid in enumerate(self.engine.hand):
            print(f"  [{i}] {cid}")
        self.input_context = {
            "kind": "mulligan_bottom",
            "required": self.mulligan_count,
        }

    def _process_context(self, text):
        c = self.input_context
        kind = c["kind"]

        if kind == "mulligan_confirm":
            value = text.lower()
            if value not in {"y", "yes", "n", "no"}:
                print("Enter y or n.")
                return

            if value in {"y", "yes"}:
                self.mulligan_waiting_for_state = True
                self._waiting_for_server_input = True
                self._send(build_mulligan_choice(self.engine.seq_num, False, []))
                self.input_context = None
                return

            print("\nMulligan cancelled. You are keeping this hand.")
            self._prompt_mulligan_bottom()
            return

        if kind == "mulligan_keep":
            value = text.lower()
            if value not in {"y", "yes", "n", "no"}:
                print("Enter y or n.")
                return

            keep = value in {"y", "yes"}

            if not keep:
                # A mulligan choice only declares that the current hand is
                # being rejected. Cards are NOT bottomed at this point.
                # The server deals the replacement hand and sends a fresh
                # GAME_STATE_UPDATE; the next keep decision happens then.
                self.mulligan_waiting_for_state = True
                self._waiting_for_server_input = True
                self._send(build_mulligan_choice(self.engine.seq_num, False, []))
                self.input_context = None
                return

            self._prompt_mulligan_bottom()
            return

        if kind == "mulligan_bottom":
            indexes = [x.strip() for x in text.split(",") if x.strip()]
            if len(indexes) != c["required"]:
                print(f"Choose exactly {c['required']} card(s).")
                return

            bottoms = []
            try:
                for value in indexes:
                    idx = int(value)
                    if not 0 <= idx < len(self.engine.hand):
                        raise ValueError
                    card_id = self.engine.hand[idx]
                    if card_id in bottoms:
                        raise ValueError
                    bottoms.append(card_id)
            except ValueError:
                print("Invalid card index list. Use distinct indexes from your hand.")
                return

            self.mulligan_waiting_for_state = True
            self._waiting_for_server_input = True
            self._send(build_mulligan_choice(self.engine.seq_num, True, bottoms))
            self.input_context = None
            return

        if kind == "land":
            card_id = self._choose_from(text, c["cards"])
            if card_id is None:
                print("Invalid land selection.")
                return
            self._send(build_play_land(self.engine.seq_num, card_id))
            self.input_context = None
            return

        if kind == "cast_card":
            card_id = self._choose_from(text, c["cards"])
            if card_id is None:
                print("Invalid spell selection.")
                return
            card = self._card(card_id)
            effect = card.get("Simplified Effect", "")
            needs_target = any(x in effect.lower() for x in ["any target", "target player", "target creature", "target spell", "target permanent", "target artifact", "target enchantment", "target noncreature"])
            c.update({"kind": "cast_target", "card_id": card_id, "needs_target": needs_target, "effect": effect})
            if needs_target:
                targets = self._legal_target_choices(effect)
                c["targets"] = targets
                print("Choose a target:")
                for i, target in enumerate(targets):
                    print(f"  [{i}] {target}")
            else:
                c["targets"] = []
                print("No target required.")
                print("Mana payment: enter entries such as R=1,C=1 (or press Enter to use the card's default color cost).")
                c["kind"] = "cast_payment"
            return

        if kind == "cast_target":
            if not c["needs_target"]:
                c["kind"] = "cast_payment"
            else:
                target = self._choose_from(text, c["targets"])
                if target is None:
                    print("Invalid target.")
                    return
                c["targets"] = [target]
                print("Mana payment: enter entries such as R=1,C=1, or press Enter for the card's required colors.")
                c["kind"] = "cast_payment"
            if kind == "cast_target" and c["needs_target"]:
                return

        if kind == "cast_payment":
            payment = self._parse_payment(text, c["card_id"])
            if payment is None:
                return
            self._send(build_cast_spell(self.engine.seq_num, c["card_id"], c["targets"], payment))
            self.input_context = None
            return

        if kind == "ability_source":
            try:
                source = c["permanents"][int(text)]
            except (ValueError, IndexError):
                source_id = self._choose_from(text, [p.get("id") for p in c["permanents"]])
                if source_id is None:
                    print("Invalid permanent selection.")
                    return
                source = next(p for p in c["permanents"] if p.get("id") == source_id)
            source_id = source.get("id")
            card = self._card(source_id)
            effects = [x.strip() for x in card.get("Simplified Effect", "").split(".") if x.strip()]
            if not effects:
                print("This permanent has no parsed abilities available to activate.")
                self.input_context = None
                return
            print("\nChoose an ability:")
            for i, effect in enumerate(effects):
                print(f"  [{i}] {effect}")
            c.update({"kind": "ability_index", "source_id": source_id, "effects": effects})
            return

        if kind == "ability_index":
            try:
                idx = int(text)
                if not 0 <= idx < len(c["effects"]):
                    raise ValueError
            except ValueError:
                print("Invalid ability index.")
                return
            effect = c["effects"][idx]
            needs_target = any(x in effect.lower() for x in ["any target", "target player", "target creature", "target permanent", "target artifact", "target enchantment"])
            c.update({"kind": "ability_target", "ability_index": idx, "effect": effect, "needs_target": needs_target})
            if needs_target:
                targets = self._legal_target_choices(effect)
                c["targets"] = targets
                print("Choose a target:")
                for i, target in enumerate(targets):
                    print(f"  [{i}] {target}")
            else:
                c["targets"] = []
                self._print_ability_payment_hint(effect)
                c["kind"] = "ability_payment"
            return

        if kind == "ability_target":
            if c["needs_target"]:
                target = self._choose_from(text, c["targets"])
                if target is None:
                    print("Invalid target.")
                    return
                c["targets"] = [target]
            self._print_ability_payment_hint(c["effect"])
            c["kind"] = "ability_payment"
            return

        if kind == "ability_payment":
            payment = self._parse_ability_payment(text)
            if payment is None:
                return
            self._send(build_activate_ability(self.engine.seq_num, c["source_id"], c["ability_index"], c["targets"], payment))
            self.input_context = None
            return

        if kind == "attackers":
            attackers = []
            if text:
                try:
                    for part in text.split(","):
                        idx = int(part.strip())
                        creature = c["creatures"][idx]
                        attackers.append({"creature_id": creature.get("id"), "target": self._opponent_id()})
                except (ValueError, IndexError):
                    print("Invalid attacker indexes.")
                    return
            self._send(build_declare_attackers(self.phase_action_seq, attackers))
            self.input_context = None
            return

        if kind == "blocker_source":
            try:
                blocker = c["creatures"][int(text)]
            except (ValueError, IndexError):
                print("Invalid blocker index.")
                return
            attackers = [x for x in self.engine.battlefield.get(self._opponent_id(), []) if x.get("attacking")]
            if not attackers:
                print("No visible attackers to block.")
                self.input_context = None
                return
            print("Choose attacker to block:")
            for i, attacker in enumerate(attackers):
                print(f"  [{i}] {attacker.get('id')}")
            c.update({"kind": "block_target", "blocker": blocker, "attackers": attackers})
            return

        if kind == "block_target":
            try:
                attacker = c["attackers"][int(text)]
            except (ValueError, IndexError):
                print("Invalid attacker index.")
                return
            blocker = c["blocker"]
            self._send(build_declare_blockers(self.phase_action_seq, [{"creature_id": blocker.get("id"), "blocking_id": attacker.get("id")}]))
            self.input_context = None
            return

        if kind == "damage_attacker":
            attackers = [
                perm.get("id") for perm in self.engine.battlefield.get(self._opponent_id(), [])
                if perm.get("attacking") and perm.get("id")
            ]
            attacker_id = self._choose_from(text, attackers) if attackers else text
            if attacker_id is None:
                print("Invalid attacker selection.")
                return
            c.update({"kind": "damage_blockers", "attacker_id": attacker_id})
            print("Blocker order, comma-separated card ids (or empty):")
            return

        if kind == "damage_blockers":
            blockers = [x.strip() for x in text.split(",") if x.strip()]
            self._send(build_assign_damage_order(self.phase_action_seq, c["attacker_id"], blockers))
            self.input_context = None
            return

        if kind == "discard":
            indexes = [x.strip() for x in text.split(",") if x.strip()]
            try:
                ids = [c["cards"][int(x)] for x in indexes]
            except (ValueError, IndexError):
                print("Invalid discard indexes.")
                return
            if len(ids) != c["count"]:
                print(f"You must choose exactly {c['count']} card(s).")
                return
            self._send(build_discard(self.cleanup_action_seq or self.engine.seq_num, ids))
            self.input_context = None
            return

    def _parse_payment(self, text, card_id):
        card = self._card(card_id)
        if not text.strip():
            payment = {c: int(card.get(c, 0)) for c in "WUBRG" if int(card.get(c, 0))}
            generic = int(card.get("Generic", 0))
            if generic:
                payment["C"] = generic
            return payment
        return self._parse_mana_entries(text)

    def _parse_mana_entries(self, text):
        payment = {}
        try:
            for entry in text.split(","):
                key, value = entry.split("=", 1)
                key = key.strip().upper()
                if key not in {"W", "U", "B", "R", "G", "C", "X"}:
                    raise ValueError
                amount = int(value.strip())
                if amount < 0:
                    raise ValueError
                payment[key] = payment.get(key, 0) + amount
        except ValueError:
            print("Invalid mana payment. Example: R=1,C=1")
            return None
        return payment

    def _print_ability_payment_hint(self, effect):
        required = self._ability_default_payment(effect)
        if required["tap"] or required["mana"]:
            print(f"Payment (press Enter for default): tap={required['tap']}, mana={required['mana']}")
        else:
            print("Payment: press Enter for no explicit cost, or enter mana as R=1,C=1 and optionally tap=y.")

    def _ability_default_payment(self, effect):
        import re
        text = effect.upper()
        tap_required = text.startswith("TAP:") or "TAP:" in text[:8]
        mana = {}
        for symbol in re.findall(r"\{([WUBRGC0-9]+)\}", text):
            if symbol in "WUBRG":
                mana[symbol] = mana.get(symbol, 0) + 1
            elif symbol.isdigit():
                mana["C"] = mana.get("C", 0) + int(symbol)
        return {"tap": tap_required, "mana": mana}

    def _parse_ability_payment(self, text):
        if not text.strip():
            # Default to the explicit activation requirements encoded in the card effect.
            effect = self.input_context.get("effect", "") if self.input_context else ""
            return self._ability_default_payment(effect)
        tap = False
        mana_text = text
        parts = [p.strip() for p in text.split(";") if p.strip()]
        if parts and parts[0].lower() in {"tap=y", "tap=yes", "tap=true"}:
            tap = True
            mana_text = ";".join(parts[1:])
        if not mana_text.strip():
            return {"tap": tap, "mana": {}}
        mana = self._parse_mana_entries(mana_text.replace(";", ","))
        if mana is None:
            return None
        return {"tap": tap, "mana": mana}

    def _opponent_id(self):
        for pid in self.engine.life_totals:
            if pid != self.player_id:
                return pid
        return None

    def _send_heartbeat_pdu(self, pdu: dict):
        """Thread-safe heartbeat send path shared with normal client sends."""
        with self._send_lock:
            send_pdu(self.sock, pdu)
            self.logger.log_pdu("C->S", pdu)

    def _send(self, pdu: dict):
        try:
            with self._send_lock:
                send_pdu(self.sock, pdu)
                self.logger.log_pdu("C->S", pdu)
        except Exception as e:
            print(f"Send failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTGNP Player Client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host IP")
    parser.add_argument("--port", type=int, default=4444, help="Server port")
    parser.add_argument("--id", required=True, help="Unique Player ID")
    parser.add_argument("--session-id", default="test-game", help="Game session ID (must match the other client)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose PDU logging")
    args = parser.parse_args()
    MTGNPClient(host=args.host, port=args.port, player_id=args.id, verbose=args.verbose, session_id=args.session_id).connect()
