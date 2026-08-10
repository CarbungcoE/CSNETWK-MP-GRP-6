from mtgnp.game.game_state import GameState
from mtgnp.game.lifecycle import GameLifecycle
from mtgnp.game.turn import TurnEngine
from mtgnp.game.priority import PriorityManager
from mtgnp.game.stack import StackManager
from mtgnp.game.combat import CombatSystem
from mtgnp.game.card_catalog import CardCatalog


class GameSession:
    """
    Represents one authoritative game session.

    GameSession owns the single GameState instance and
    provides access to the systems that operate on it.
    """

    def __init__(self):
        self.state = GameState()

        self.lifecycle = GameLifecycle(
            self.state
        )

        self.turn = TurnEngine(
            self.state
        )

        self.priority = PriorityManager(
            self.state
        )

        self.stack = StackManager(
            self.state
        )

        self.combat = CombatSystem(
            self.state
        )

        self.cards = CardCatalog()
        self._stack_counter = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def player_ready(
        self,
        player_id: str,
        deck_list: list,
    ):
        return self.lifecycle.process_player_ready(
            player_id,
            deck_list,
        )

    def start_setup(self):
        self.lifecycle.setup_game()

    def process_mulligan(
        self,
        player_id: str,
        keep: bool,
        cards_to_bottom: list,
    ):
        return self.lifecycle.process_mulligan(
            player_id,
            keep,
            cards_to_bottom,
        )

    def is_mulligan_complete(self) -> bool:
        return self.lifecycle.is_mulligan_complete()

    def get_visible_state(
        self,
        player_id: str,
    ):
        return self.lifecycle.generate_visible_state(
            player_id
        )

    # ------------------------------------------------------------------
    # Turn
    # ------------------------------------------------------------------

    def start_game(self):
        return self.turn.start_game()

    def begin_turn(self):
        self.turn.begin_turn()

    def advance_phase(self):
        return self.turn.advance_phase()

    def requires_priority(self) -> bool:
        return self.turn.requires_priority()

    # ------------------------------------------------------------------
    # Priority
    # ------------------------------------------------------------------

    def grant_priority(
        self,
        player_id: str,
    ) -> int:
        return self.priority.grant_priority(
            player_id
        )

    def pass_priority(self):
<<<<<<< HEAD
        """Pass priority, resolve the stack when both players pass, or advance the step."""
        if self.state.game_over:
            raise ValueError("Cannot pass priority after game over")
        if self.state.priority_player is None:
            raise ValueError("Cannot pass priority when nobody has priority")
=======
        """
        Record a priority pass and advance the phase after all players
        have passed consecutively.

        Returns a result dictionary so the socket layer can distinguish
        a normal priority transfer from a phase transition.
        """
        if self.state.game_over:
            raise ValueError(
                "Cannot pass priority after game over"
            )

        if self.state.priority_player is None:
            raise ValueError(
                "Cannot pass priority when nobody has priority"
            )
>>>>>>> 979dab4927d958bbfeba6ba88cf8fd8de7fcae04

        player_count = len(self.state.players)
        if player_count == 0:
            raise ValueError("Cannot pass priority without players")

<<<<<<< HEAD
        self.state.consecutive_passes += 1

        if self.state.consecutive_passes < player_count:
            next_player = self.priority.pass_priority()
=======
        if player_count == 0:
            raise ValueError(
                "Cannot pass priority without players"
            )

        self.state.consecutive_passes += 1

        # Normal pass: transfer priority to the other player.
        if self.state.consecutive_passes < player_count:
            next_player = self.priority.pass_priority()

>>>>>>> 979dab4927d958bbfeba6ba88cf8fd8de7fcae04
            return {
                "advanced": False,
                "priority_player": next_player,
                "priority_seq_num": self.state.priority_seq_num,
            }

<<<<<<< HEAD
        self.state.consecutive_passes = 0

        if not self.stack.is_empty():
            item = self.resolve_stack()
            resolved = self._resolve_stack_item(item)
            self._check_state_based_actions()

            if not self.state.game_over:
                self.grant_active_player_priority()

            return {
                "advanced": False,
                "stack_resolved": True,
                "resolved": resolved,
                "priority_player": self.state.priority_player,
                "priority_seq_num": self.state.priority_seq_num,
                "phase": self.state.phase,
                "turn": self.state.turn,
                "active_player": self.state.active_player,
            }

        transitions = []
        while True:
            from_phase = self.state.phase
            to_phase = self.turn.advance_phase()
            transitions.append({"from_phase": from_phase, "to_phase": to_phase})
=======
        # All players passed. Advance through any automatic
        # phases/steps until the next priority-bearing phase.
        self.state.consecutive_passes = 0

        transitions = []

        while True:
            from_phase = self.state.phase
            to_phase = self.turn.advance_phase()

            transitions.append({
                "from_phase": from_phase,
                "to_phase": to_phase,
            })

>>>>>>> 979dab4927d958bbfeba6ba88cf8fd8de7fcae04
            if self.turn.requires_priority():
                self.grant_active_player_priority()
                break

        return {
            "advanced": True,
            "transitions": transitions,
            "priority_player": self.state.priority_player,
            "priority_seq_num": self.state.priority_seq_num,
            "phase": self.state.phase,
            "turn": self.state.turn,
            "active_player": self.state.active_player,
        }

    def grant_active_player_priority(self):
        return self.priority.grant_active_player_priority()

    def has_priority(
        self,
        player_id: str,
    ) -> bool:
        return self.priority.has_priority(
            player_id
        )

    def get_priority_seq_num(self) -> int:
        return self.state.priority_seq_num

    def validate_priority_seq_num(
        self,
        seq_num: int,
    ) -> bool:
        return self.priority.validate_seq_num(
            seq_num
        )

    def cast_spell(self, player_id: str, card_id: str, targets: list, mana_payment: dict) -> dict:
        if self.state.game_over:
            raise ValueError("Cannot cast a spell after game over")
        if self.state.priority_player != player_id:
            raise ValueError("NOT_PRIORITY_PLAYER")
        player = self.state.players.get(player_id)
        if player is None:
            raise ValueError("NOT_IN_GAME")
        if card_id not in player.hand:
            raise ValueError("ILLEGAL_ACTION")
        card = self.cards.get_by_instance_id(card_id)
        if card is None or card["Card Type"] == "Land":
            raise ValueError("ILLEGAL_ACTION")
        if card["Card Type"] in {"Sorcery", "Creature", "Enchantment", "Artifact", "Artifact Creature"}:
            if self.state.phase not in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"} or self.state.active_player != player_id:
                raise ValueError("WRONG_PHASE")
        if not isinstance(targets, list) or not isinstance(mana_payment, dict):
            raise ValueError("ILLEGAL_ACTION")
        self._validate_targets(card, targets)
        self._pay_mana(player, card, mana_payment)
        player.hand.remove(card_id)
        self._stack_counter += 1
        stack_id = f"stk_{self._stack_counter:03d}"
        item = {"stack_item_id": stack_id, "item_type": "SPELL", "source_id": card_id, "controller_id": player_id, "targets": list(targets), "card": card}
        self.push_stack(item)
        self.state.consecutive_passes = 0
        self.grant_priority(player_id)
        return {"stack_item_id": stack_id, "item_type": "SPELL", "source": card_id, "targets": list(targets), "controller": player_id, "priority_player": player_id, "priority_seq_num": self.state.priority_seq_num}

    def _pay_mana(self, player, card, payment):
        try:
            normalized = {k: int(v) for k, v in payment.items()}
        except (TypeError, ValueError):
            raise ValueError("ILLEGAL_ACTION")
        if any(v < 0 for v in normalized.values()) or any(k not in {"W","U","B","R","G","C"} for k in normalized):
            raise ValueError("ILLEGAL_ACTION")
        required = {c: card[c] for c in "WUBRG"}
        for c in "WUBRG":
            if normalized.get(c, 0) < required[c]:
                raise ValueError("INSUFFICIENT_MANA")
        total_payment = sum(normalized.get(c, 0) for c in "WUBRG") + normalized.get("C", 0)
        if total_payment != card["CMC"]:
            raise ValueError("INSUFFICIENT_MANA")
        untapped = [p for p in player.battlefield if not p.get("tapped", False)]
        produces = {"mountain":"R", "forest":"G", "plains":"W", "island":"U", "swamp":"B"}
        available = {c: [] for c in "WUBRG"}
        for permanent in untapped:
            color = produces.get(permanent.get("id", "").rsplit("_", 1)[0])
            if color:
                available[color].append(permanent)
        chosen = []
        for c in "WUBRG":
            for _ in range(normalized.get(c, 0)):
                if not available[c]:
                    raise ValueError("INSUFFICIENT_MANA")
                chosen.append(available[c].pop())
        generic = normalized.get("C", 0)
        remaining = [p for p in untapped if p not in chosen]
        if generic > len(remaining):
            raise ValueError("INSUFFICIENT_MANA")
        chosen.extend(remaining[:generic])
        if len(chosen) != total_payment:
            raise ValueError("INSUFFICIENT_MANA")
        for permanent in chosen:
            permanent["tapped"] = True

    def _validate_targets(self, card, targets):
        effect = card["Simplified Effect"].lower()
        needs_target = "target" in effect or "any target" in effect
        if needs_target and len(targets) != 1:
            raise ValueError("ILLEGAL_ACTION")
        if not needs_target and targets:
            raise ValueError("ILLEGAL_ACTION")
        if not targets:
            return
        target = targets[0]
        if target in self.state.players:
            if "creature" in effect and "any target" not in effect:
                raise ValueError("ILLEGAL_TARGET")
            return
        battlefield_targets = [c for p in self.state.players.values() for c in p.battlefield if c.get("id") == target]
        if battlefield_targets:
            if "player" in effect and "any target" not in effect and "creature" not in effect:
                raise ValueError("ILLEGAL_TARGET")
            return
        if "counter target spell" in effect and any(s.get("stack_item_id") == target for s in self.state.stack):
            return
        raise ValueError("ILLEGAL_TARGET")

    def _resolve_stack_item(self, item):
        if item is None:
            return {"result": "FIZZLE", "stack_item_id": None, "state_changes": []}
        card = item["card"]
        effect = card["Simplified Effect"].lower()
        source_id = item["source_id"]
        controller = self.state.players[item["controller_id"]]
        targets = item.get("targets", [])
        changes = []
        result = "RESOLVED"
        if targets:
            for target in targets:
                if target in self.state.players or any(c.get("id") == target for p in self.state.players.values() for c in p.battlefield):
                    continue
                if "counter target spell" in effect and any(s.get("stack_item_id") == target for s in self.state.stack):
                    continue
                result = "FIZZLE"
                break
        if result == "RESOLVED":
            if "counter target spell" in effect:
                target_id = targets[0]
                self.state.stack[:] = [s for s in self.state.stack if s.get("stack_item_id") != target_id]
                changes.append({"type":"COUNTER","target":target_id})
            elif "deals 4 damage" in effect or "deals 3 damage" in effect or "deals 2 damage" in effect:
                amount = 4 if "deals 4 damage" in effect else (3 if "deals 3 damage" in effect else 2)
                target = targets[0]
                if target in self.state.players:
                    self.state.players[target].life -= amount
                    changes.append({"type":"DAMAGE","target":target,"amount":amount})
                else:
                    for p in self.state.players.values():
                        for permanent in p.battlefield:
                            if permanent.get("id") == target:
                                permanent["damage"] = permanent.get("damage", 0) + amount
                                changes.append({"type":"DAMAGE","target":target,"amount":amount})
                                break
            elif card["Card Type"] in {"Creature", "Artifact Creature"}:
                permanent = {"id":source_id,"power":card["Power"],"toughness":card["Toughness"],"damage":0,"tapped":False,"summoning_sickness":True,"haste":"haste" in effect}
                controller.battlefield.append(permanent)
                changes.append({"type":"ENTER_BATTLEFIELD","card_id":source_id})
        if card["Card Type"] not in {"Creature", "Artifact Creature"} and result == "RESOLVED":
            controller.graveyard.append({"id": source_id, "card": card})
        elif card["Card Type"] in {"Creature", "Artifact Creature"} and result == "FIZZLE":
            controller.graveyard.append({"id": source_id, "card": card})
        return {"result": result, "stack_item_id": item["stack_item_id"], "state_changes": changes}

    def _check_state_based_actions(self):
        for player_id, player in self.state.players.items():
            if player.life <= 0:
                self.state.game_over = True
                self.state.winner = next((pid for pid in self.state.players if pid != player_id), None)
                self.state.game_over_reason = "LIFE_ZERO"
                return
        for player in self.state.players.values():
            survivors = []
            for permanent in player.battlefield:
                if "toughness" in permanent and permanent.get("damage", 0) >= permanent.get("toughness", 1):
                    player.graveyard.append(permanent)
                elif "toughness" in permanent and permanent.get("toughness", 0) <= 0:
                    player.graveyard.append(permanent)
                else:
                    survivors.append(permanent)
            player.battlefield = survivors

    def play_land(
        self,
        player_id: str,
        card_id: str,
    ) -> dict:
        """Play a land during a Main Phase.

        Playing a land does not use the stack. The Active Player keeps
        priority after a successful land play.
        """
        if self.state.game_over:
            raise ValueError("Cannot play a land after game over")

        if self.state.phase not in {
            "PRECOMBAT_MAIN",
            "POSTCOMBAT_MAIN",
        }:
            raise ValueError("WRONG_PHASE")

        if self.state.active_player != player_id:
            raise ValueError("NOT_ACTIVE_PLAYER")

        if self.state.priority_player != player_id:
            raise ValueError("NOT_PRIORITY_PLAYER")

        player = self.state.players.get(player_id)
        if player is None:
            raise ValueError("NOT_IN_GAME")

        if player.land_played_this_turn:
            raise ValueError("LAND_PLAYED_THIS_TURN")

        if not card_id or card_id not in player.hand:
            raise ValueError("ILLEGAL_ACTION")

        # MTGNP uses the fixed predefined card set. Land instance IDs
        # use the card base followed by an instance suffix, e.g.
        # mountain_001. Keep the rule local to the game system rather
        # than trusting the client-provided card type.
        land_bases = {
            "mountain",
            "forest",
            "plains",
            "island",
            "swamp",
        }
        card_base = card_id.rsplit("_", 1)[0]

        if card_base not in land_bases:
            raise ValueError("ILLEGAL_ACTION")

        player.hand.remove(card_id)
        player.battlefield.append({
            "id": card_id,
            "tapped": False,
        })
        player.land_played_this_turn = True

        return {
            "card_id": card_id,
            "player_id": player_id,
            "phase": self.state.phase,
            "priority_player": self.state.priority_player,
            "priority_seq_num": self.state.priority_seq_num,
        }

    # ------------------------------------------------------------------
    # Mulligan sequence
    # ------------------------------------------------------------------

    def set_mulligan_seq(
        self,
        player_id: str,
        seq_num: int,
    ) -> None:
        self.state.mulligan_seq_nums[
            player_id
        ] = seq_num

    def get_mulligan_seq(
        self,
        player_id: str,
    ) -> int | None:
        return self.state.mulligan_seq_nums.get(
            player_id
        )

    def validate_mulligan_seq(
        self,
        player_id: str,
        seq_num: int,
    ) -> bool:
        expected = self.get_mulligan_seq(
            player_id
        )

        return (
            expected is not None
            and expected == seq_num
        )

    # ------------------------------------------------------------------
    # Stack
    # ------------------------------------------------------------------

    def push_stack(self, item: dict):
        self.stack.push(item)

    def pop_stack(self):
        return self.stack.pop()

    def peek_stack(self):
        return self.stack.peek()

    def resolve_stack(self):
        return self.stack.resolve_top()

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def declare_attackers(
        self,
        player_id: str,
        attackers: list,
    ):
        return self.combat.declare_attackers(
            player_id,
            attackers,
        )

    def declare_blockers(
        self,
        player_id: str,
        blockers: list,
    ):
        return self.combat.declare_blockers(
            player_id,
            blockers,
        )

    def check_damage_order_needed(self):
        return self.combat.check_damage_order_needed()

    def resolve_combat(
        self,
        seq_num: int,
    ):
        return self.combat.resolve_combat(
            seq_num
        )

    def clear_combat(self):
        self.combat.clear_combat()