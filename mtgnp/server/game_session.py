from mtgnp.game.game_state import GameState
from mtgnp.game.lifecycle import GameLifecycle
from mtgnp.game.turn import TurnEngine
from mtgnp.game.priority import PriorityManager
from mtgnp.game.stack import StackManager
from mtgnp.game.combat import CombatSystem
from mtgnp.game.card_catalog import CardCatalog
<<<<<<< HEAD
import re
=======
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108


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
        if self.state.game_over: raise ValueError("Cannot pass priority after game over")
        if self.state.priority_player is None: raise ValueError("Cannot pass priority when nobody has priority")
        if len(self.state.players) < 2: raise ValueError("Cannot pass priority without players")
        self.state.consecutive_passes += 1
        if self.state.consecutive_passes < len(self.state.players):
            nxt=self.priority.pass_priority()
            return {"advanced":False,"priority_player":nxt,"priority_seq_num":self.state.priority_seq_num}
        self.state.consecutive_passes=0
        if not self.stack.is_empty():
            item=self.resolve_stack(); resolved=self._resolve_stack_item(item); self._check_state_based_actions()
            if self.state.game_over:
                return {"advanced":False,"stack_resolved":True,"resolved":resolved,"game_over":True}
            self.grant_active_player_priority()
            return {"advanced":False,"stack_resolved":True,"resolved":resolved,"priority_player":self.state.priority_player,"priority_seq_num":self.state.priority_seq_num,"phase":self.state.phase,"turn":self.state.turn,"active_player":self.state.active_player}
        transitions=[]
        combat_results=[]
        # If this was a declaration/ordering priority window, advance after the completed declaration.
        if self.state.phase in {"DECLARE_ATTACKERS","DECLARE_BLOCKERS","ASSIGN_DAMAGE_ORDER"} and not self.state.phase_decision_complete:
            raise ValueError("DECLARATION_REQUIRED")
        while True:
            from_phase=self.state.phase
            to_phase=self.turn.advance_phase()
            transitions.append({"from_phase":from_phase,"to_phase":to_phase})
            if to_phase in {"DECLARE_ATTACKERS","DECLARE_BLOCKERS","ASSIGN_DAMAGE_ORDER"}:
                self.state.priority_player=None
                if to_phase == "ASSIGN_DAMAGE_ORDER" and not self.combat.check_damage_order_needed():
                    self.state.phase_decision_complete=True
                    continue
                break
            if to_phase == "FIRST_STRIKE_DAMAGE":
                has_fs=any(c.get("first_strike") or c.get("double_strike") for p in self.state.players.values() for c in p.battlefield if c.get("attacking") or any(a.get("creature_id")==c.get("id") for a in self.combat.atks))
                if has_fs:
                    result=self.resolve_combat_damage(True); self._check_state_based_actions(); combat_results.append(result)
                    transitions.append({"automatic":"FIRST_STRIKE_DAMAGE","result":result})
                # Continue automatically into normal combat damage.
                from_phase=self.state.phase; to_phase=self.turn.advance_phase(); transitions.append({"from_phase":from_phase,"to_phase":to_phase})
            if self.state.phase == "COMBAT_DAMAGE":
                result=self.resolve_combat_damage(False); self._check_state_based_actions(); combat_results.append(result); transitions.append({"automatic":"COMBAT_DAMAGE","result":result})
                self.clear_combat()
                from_phase=self.state.phase; to_phase=self.turn.advance_phase(); transitions.append({"from_phase":from_phase,"to_phase":to_phase})
            if self.state.game_over:
                break
            if self.turn.requires_priority():
                self.grant_active_player_priority(); break
            if self.state.phase == "CLEANUP":
                # Hand-size cleanup is mandatory only when needed; otherwise proceed to next turn.
                oversized=[pid for pid,p in self.state.players.items() if len(p.hand)>7]
                if oversized:
                    self.state.priority_player=None; break
                from_phase=self.state.phase; to_phase=self.turn.advance_phase(); transitions.append({"from_phase":from_phase,"to_phase":to_phase})
                if self.turn.requires_priority(): self.grant_active_player_priority(); break
                # _end_turn starts the next turn when CLEANUP is advanced.
        return {"advanced":True,"transitions":transitions,"priority_player":self.state.priority_player,"priority_seq_num":self.state.priority_seq_num,"phase":self.state.phase,"turn":self.state.turn,"active_player":self.state.active_player,"game_over":self.state.game_over,"combat_results":combat_results}
=======
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
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108

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
<<<<<<< HEAD
        ctype = card["Card Type"]
        if ctype in {"Sorcery", "Creature", "Enchantment", "Artifact", "Artifact Creature"}:
            if self.state.phase not in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"} or self.state.active_player != player_id:
                raise ValueError("WRONG_PHASE")
        if ctype in {"Instant", "Sorcery"} or ctype in {"Creature", "Artifact Creature", "Enchantment", "Artifact"}:
            pass
=======
        if card["Card Type"] in {"Sorcery", "Creature", "Enchantment", "Artifact", "Artifact Creature"}:
            if self.state.phase not in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"} or self.state.active_player != player_id:
                raise ValueError("WRONG_PHASE")
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108
        if not isinstance(targets, list) or not isinstance(mana_payment, dict):
            raise ValueError("ILLEGAL_ACTION")
        self._validate_targets(card, targets)
        self._pay_mana(player, card, mana_payment)
        player.hand.remove(card_id)
        self._stack_counter += 1
        stack_id = f"stk_{self._stack_counter:03d}"
<<<<<<< HEAD
        item = {"stack_item_id": stack_id, "item_type": "SPELL", "source_id": card_id,
                "controller_id": player_id, "targets": list(targets), "card": card}
        self.push_stack(item)
        for target in targets:
            pid_t, perm_t = self._find_permanent(target)
            if perm_t and target.rsplit("_",1)[0] == "phantasmal_bear":
                self._stack_counter += 1
                self.state.stack.append({"stack_item_id":f"trg_{self._stack_counter:03d}","item_type":"TRIGGER_ABILITY","source_id":target,"controller_id":pid_t,"targets":[],"trigger_effect":"PHANTASMAL_BEAR_TARGET"})
        if card["Card Type"] not in {"Creature", "Artifact Creature"}:
            for perm in player.battlefield:
                if perm.get("prowess"): perm["temp_power"]=perm.get("temp_power",0)+1; perm["temp_toughness"]=perm.get("temp_toughness",0)+1
        self.state.consecutive_passes = 0
        self.grant_priority(player_id)
        return {"stack_item_id": stack_id, "item_type": "SPELL", "source": card_id,
                "targets": list(targets), "controller": player_id,
                "priority_player": player_id, "priority_seq_num": self.state.priority_seq_num}

    def _pay_mana(self, player, card, payment):
        try:
            normalized = {k.upper(): int(v) for k, v in payment.items()}
        except (TypeError, ValueError):
            raise ValueError("ILLEGAL_ACTION")
        if any(v < 0 for v in normalized.values()) or any(k not in {"W","U","B","R","G","C","X"} for k in normalized):
            raise ValueError("ILLEGAL_ACTION")
        required = {c: int(card[c]) for c in "WUBRG"}
        for c in "WUBRG":
            if normalized.get(c, 0) < required[c]:
                raise ValueError("INSUFFICIENT_MANA")
        total = sum(normalized.get(c, 0) for c in "WUBRG") + normalized.get("C", normalized.get("X", 0))
        if total != int(card["CMC"]):
            raise ValueError("INSUFFICIENT_MANA")
        # Explicit payment describes the mana sources to tap. Use pool first,
        # then battlefield permanents that produce the requested color.
        for c in "WUBRG":
            need = normalized.get(c, 0)
            from_pool = min(need, player.mana_pool.get(c, 0))
            player.mana_pool[c] -= from_pool
            need -= from_pool
            if need:
                self._tap_mana_sources(player, c, need)
        generic = normalized.get("C", normalized.get("X", 0))
        pool_generic = min(generic, player.mana_pool.get("C", 0))
        player.mana_pool["C"] -= pool_generic
        generic -= pool_generic
        if generic:
            for c in "WUBRG":
                take = min(generic, player.mana_pool.get(c, 0))
                player.mana_pool[c] -= take
                generic -= take
                if generic == 0: break
        if generic:
            # Tap any remaining untapped mana source for generic mana.
            sources = self._untapped_mana_sources(player)
            if len(sources) < generic:
                raise ValueError("INSUFFICIENT_MANA")
            for src in sources[:generic]: src["tapped"] = True

    def _untapped_mana_sources(self, player):
        bases = {"mountain":"R","forest":"G","plains":"W","island":"U","swamp":"B",
                 "llanowar_elves":"G","elvish_mystic":"G","sol_ring":"C"}
        return [p for p in player.battlefield if not p.get("tapped") and p.get("id", "").rsplit("_",1)[0] in bases]

    def _tap_mana_sources(self, player, color, count):
        bases = {"mountain":"R","forest":"G","plains":"W","island":"U","swamp":"B",
                 "llanowar_elves":"G","elvish_mystic":"G","sol_ring":"C"}
        sources=[p for p in self._untapped_mana_sources(player) if bases.get(p.get("id", "").rsplit("_",1)[0]) == color]
        if len(sources) < count:
            raise ValueError("INSUFFICIENT_MANA")
        for src in sources[:count]: src["tapped"] = True

    def _validate_targets(self, card, targets):
        effect = card["Simplified Effect"].lower()
        needs_target = any(x in effect for x in ["any target", "target player", "target creature", "target spell", "target permanent", "target artifact", "target enchantment", "target noncreature"])
        if not needs_target:
            if targets:
                raise ValueError("ILLEGAL_TARGET")
            return
        if not targets:
            raise ValueError("ILLEGAL_TARGET")
        for target in targets:
            if target in self.state.players:
                if "creature" in effect and "any target" not in effect and "target player" not in effect:
                    raise ValueError("ILLEGAL_TARGET")
                continue
            perm = next((c for p in self.state.players.values() for c in p.battlefield if c.get("id") == target), None)
            if "spell" in effect and not any(s.get("stack_item_id") == target for s in self.state.stack):
                raise ValueError("ILLEGAL_TARGET")
            if "spell" in effect and any(s.get("stack_item_id") == target for s in self.state.stack):
                continue
            if perm is None:
                raise ValueError("ILLEGAL_TARGET")
            base=self.cards.get_by_instance_id(target)
            ctype=(base or {}).get("Card Type", "")
            color=(base or {}).get("Color", "")
            if "nonartifact" in effect and ctype.startswith("Artifact"):
                raise ValueError("ILLEGAL_TARGET")
            if "nonblack" in effect and color == "B":
                raise ValueError("ILLEGAL_TARGET")
            if "artifact" in effect and "nonartifact" not in effect and not ctype.startswith("Artifact"):
                raise ValueError("ILLEGAL_TARGET")
            if "enchantment" in effect and "artifact or enchantment" in effect and ctype != "Enchantment":
                raise ValueError("ILLEGAL_TARGET")

    def _find_permanent(self, card_id):
        for pid, player in self.state.players.items():
            for c in player.battlefield:
                if c.get("id") == card_id:
                    return pid, c
        return None, None

    def _change_life(self, pid, amount, changes):
        p=self.state.players[pid]
        if amount > 0 and p.life_gain_prevented: return
        p.life += amount
        changes.append({"type":"LIFE_GAIN" if amount>0 else "DAMAGE", "target":pid, "amount":abs(amount)})

    def _resolve_stack_item(self, item):
        if item is None:
            return {"result":"FIZZLE","stack_item_id":None,"state_changes":[]}
        card=item.get("card",{})
        effect=card.get("Simplified Effect","").lower()
        if item.get("item_type") == "TRIGGER_ABILITY":
            effect=item.get("trigger_effect","").lower()
        source=item.get("source_id")
        controller_id=item.get("controller_id")
        controller=self.state.players.get(controller_id)
        targets=item.get("targets",[])
        changes=[]
        result="RESOLVED"
        # Revalidate targets at resolution time.
        if item.get("item_type") == "TRIGGER_ABILITY":
            pass
        else:
            try: self._validate_targets(card, targets)
            except ValueError: result="FIZZLE"
        if result == "RESOLVED" and item.get("item_type") == "TRIGGER_ABILITY":
            trig=item.get("trigger_effect")
            if trig == "PHANTASMAL_BEAR_TARGET":
                owner,perm=self._find_permanent(item.get("source_id"))
                if perm and owner:
                    self.state.players[owner].battlefield.remove(perm); self.state.players[owner].graveyard.append(perm); changes.append({"type":"SACRIFICE","target":item.get("source_id")})
            elif trig == "GOBLIN_GUIDE_ATTACK":
                opp=next((pid for pid in self.state.players if pid!=controller_id),None)
                if opp:
                    op=self.state.players[opp]
                    if op.library:
                        top=op.library[-1]
                        if top.rsplit("_",1)[0] in {"mountain","forest","plains","island","swamp"}:
                            op.hand.append(op.library.pop()); changes.append({"type":"REVEAL_TOP","target":opp,"card_id":top,"land":True})
                        else:
                            changes.append({"type":"REVEAL_TOP","target":opp,"card_id":top,"land":False})
            elif trig == "GRAY_MERCHANT_ETB":
                devotion=sum(1 for c in controller.battlefield if self.cards.get_by_instance_id(c.get("id","")) and self.cards.get_by_instance_id(c.get("id",""))["Color"]=="B")
                opp=next((pid for pid in self.state.players if pid!=controller_id),None)
                if opp and devotion:
                    self._change_life(opp,-devotion,changes); self._change_life(controller_id,devotion,changes)
            elif trig == "GRAVEDIGGER_ETB":
                legal=[entry.get("id") for entry in controller.graveyard if isinstance(entry,dict) and entry.get("id")] if controller else []
                if legal:
                    trigger_id=item.get("stack_item_id")
                    self.state.pending_trigger_choices[controller_id]={"trigger_id":trigger_id,"item":{**item},"requires_target":True,"legal_targets":legal,"effect_summary":"Return target creature card from your graveyard to your hand."}
                else:
                    result="FIZZLE"
            else: result="FIZZLE"
        elif result == "RESOLVED" and item.get("item_type") == "ABILITY":
            ability=item.get("ability_effect", "")
            if "draw a card" in ability and controller:
                if controller.library: controller.hand.append(controller.library.pop()); changes.append({"type":"DRAW","target":controller_id,"amount":1})
                else: result="FIZZLE"
            elif "deals 1 damage" in ability and targets:
                t=targets[0]
                if t in self.state.players: self._change_life(t,-1,changes)
                else:
                    _,perm=self._find_permanent(t)
                    if perm: perm["damage"]=perm.get("damage",0)+1; changes.append({"type":"DAMAGE","target":t,"amount":1})
            elif "destroy target tapped creature" in ability and targets:
                _,perm=self._find_permanent(targets[0])
                if perm and perm.get("tapped"):
                    owner,_=self._find_permanent(targets[0]); self.state.players[owner].battlefield.remove(perm); self.state.players[owner].graveyard.append(perm); changes.append({"type":"DESTROY","target":targets[0]})
                else: result="FIZZLE"
            elif "regenerate" in ability:
                changes.append({"type":"REGENERATE","target":source})
            elif "protection" in ability and targets:
                _,perm=self._find_permanent(targets[0]);
                if perm: perm["protection_until_turn"]=self.state.turn; changes.append({"type":"PROTECTION","target":targets[0]})
            else:
                result="FIZZLE"
        elif result == "RESOLVED":
            if "return target creature" in effect and targets:
                pid,perm=self._find_permanent(targets[0])
                if perm:
                    self.state.players[pid].battlefield.remove(perm); self.state.players[pid].hand.append(perm["id"]); changes.append({"type":"BOUNCE","target":targets[0]})
            elif "destroy target" in effect and targets:
                pid,perm=self._find_permanent(targets[0])
                if perm:
                    self.state.players[pid].battlefield.remove(perm); self.state.players[pid].graveyard.append(perm); changes.append({"type":"DESTROY","target":targets[0]})
            elif "exile target creature" in effect and targets:
                pid,perm=self._find_permanent(targets[0])
                if perm:
                    self.state.players[pid].battlefield.remove(perm); self.state.players[pid].exile.append(perm); changes.append({"type":"EXILE","target":targets[0]})
                    if "gains life equal" in effect: self._change_life(pid,perm.get("power",0),changes)
            elif "counter target spell unless its controller pays" in effect and targets:
                tid=targets[0]
                target_item=next((x for x in self.state.stack if x.get("stack_item_id")==tid),None)
                if target_item is None: result="FIZZLE"
                else:
                    payer=self.state.players.get(target_item.get("controller_id")); can_pay=False
                    if payer:
                        available=sum(payer.mana_pool.values()) + len(self._untapped_mana_sources(payer))
                        if available >= 3: can_pay=True
                    if not can_pay:
                        self.state.stack[:]=[x for x in self.state.stack if x.get("stack_item_id")!=tid]; changes.append({"type":"COUNTER","target":tid})
                    else:
                        # Automatically pay the three generic mana when available.
                        need=3
                        for c in "WUBRGC":
                            take=min(need,payer.mana_pool.get(c,0)); payer.mana_pool[c]-=take; need-=take
                            if need==0: break
                        if need:
                            for src in self._untapped_mana_sources(payer)[:need]: src["tapped"]=True
                        changes.append({"type":"MANA_PAYMENT","target":target_item.get("controller_id"),"amount":3})
            elif "counter target" in effect and targets:
                tid=targets[0]; before=len(self.state.stack)
                self.state.stack[:]=[x for x in self.state.stack if x.get("stack_item_id") != tid]
                if len(self.state.stack)==before: result="FIZZLE"
                else: changes.append({"type":"COUNTER","target":tid})
            elif "look at top 3" in effect and controller:
                top=list(reversed(controller.library[-3:]))
                changes.append({"type":"LOOK_TOP","target":controller_id,"cards":top})
                if "draw a card" in effect and controller.library:
                    controller.hand.append(controller.library.pop()); changes.append({"type":"DRAW","target":controller_id,"amount":1})
            elif "search your library for a basic land" in effect and controller:
                base_land=next((c for c in controller.library if c.rsplit("_",1)[0] in {"mountain","forest","plains","island","swamp"}),None)
                if base_land:
                    controller.library.remove(base_land)
                    controller.battlefield.append({"id":base_land,"tapped":True})
                    changes.append({"type":"SEARCH_BASIC_LAND","target":controller_id,"card_id":base_land})
                    import random; random.shuffle(controller.library)
            elif "draw a card" in effect and controller:
                if controller.library: controller.hand.append(controller.library.pop()); changes.append({"type":"DRAW","target":controller_id,"amount":1})
            elif "discard" in effect and targets:
                n=2 if "two cards" in effect else 1; tp=self.state.players.get(targets[0])
                if tp:
                    n=min(n,len(tp.hand)); tp.graveyard.extend({"id":c,"card":self.cards.get_by_instance_id(c)} for c in tp.hand[:n]); del tp.hand[:n]
                    changes.append({"type":"DISCARD","target":targets[0],"amount":n})
            elif "deals 4 damage" in effect or "deals 3 damage" in effect or "deals 2 damage" in effect or "deals 1 damage" in effect:
                amount=4 if "deals 4 damage" in effect else 3 if "deals 3 damage" in effect else 2 if "deals 2 damage" in effect else 1
                if targets:
                    t=targets[0]
                    if t in self.state.players:
                        before=self.state.players[t].life; self._change_life(t,-amount,changes); amount_done=before-self.state.players[t].life
                        if amount_done==0: changes.append({"type":"DAMAGE_PREVENTED","target":t,"amount":amount})
                    else:
                        _,perm=self._find_permanent(t)
                        if perm: perm["damage"]=perm.get("damage",0)+amount; changes.append({"type":"DAMAGE","target":t,"amount":amount})
            elif "gains 3 life" in effect and targets:
                self._change_life(targets[0],3,changes)
            elif "gain life equal" in effect and controller:
                # Simplified devotion approximation from black permanents.
                devotion=sum(1 for c in controller.battlefield if self.cards.get_by_instance_id(c.get("id","")) and self.cards.get_by_instance_id(c.get("id",""))["Color"]=="B")
                self._change_life(controller_id,devotion,changes)
            elif "destroy target" in effect and targets:
                pid,perm=self._find_permanent(targets[0])
                if perm:
                    self.state.players[pid].battlefield.remove(perm); self.state.players[pid].graveyard.append(perm); changes.append({"type":"DESTROY","target":targets[0]})
            elif "exile target creature" in effect and targets:
                pid,perm=self._find_permanent(targets[0])
                if perm:
                    self.state.players[pid].battlefield.remove(perm); self.state.players[pid].exile.append(perm); changes.append({"type":"EXILE","target":targets[0]})
                    if "gains life equal" in effect: self._change_life(pid,perm.get("power",0),changes)
            elif "return target creature" in effect and targets:
                pid,perm=self._find_permanent(targets[0])
                if perm:
                    self.state.players[pid].battlefield.remove(perm); self.state.players[pid].hand.append(perm["id"]); changes.append({"type":"BOUNCE","target":targets[0]})
            elif "return target creature card from your graveyard" in effect and controller and targets:
                target=targets[0]
                match=next((c for c in controller.graveyard if c.get("id")==target),None)
                if match: controller.graveyard.remove(match); controller.hand.append(target); changes.append({"type":"RETURN_TO_HAND","target":target})
            elif "add {b}{b}{b}" in effect and controller:
                controller.mana_pool["B"] += 3; changes.append({"type":"MANA","target":controller_id,"amount":3,"color":"B"})
            elif "add {r}" in effect or "add {g}" in effect or "add {w}" in effect or "add {u}" in effect or "add {b}" in effect:
                color=next((c for c in "WUBRG" if "add {"+c.lower()+"}" in effect),"C"); controller.mana_pool[color]+=1; changes.append({"type":"MANA","target":controller_id,"amount":1,"color":color})
            elif "add {c}{c}" in effect and controller:
                controller.mana_pool["C"] += 2; changes.append({"type":"MANA","target":controller_id,"amount":2,"color":"C"})
            elif card.get("Card Type") in {"Creature","Artifact Creature"}:
                permanent={"id":source,"power":card["Power"],"toughness":card["Toughness"],"damage":0,"tapped":False,"summoning_sickness":True,
                           "haste":"haste" in effect,"first_strike":"first strike" in effect,"double_strike":"double strike" in effect,
                           "flying":"flying" in effect,"defender":"defender" in effect,"trample":"trample" in effect,"hexproof":"hexproof" in effect,"prowess":"prowess" in effect}
                controller.battlefield.append(permanent); changes.append({"type":"ENTER_BATTLEFIELD","card_id":source})
                self._fire_triggers("ETB", source, permanent)
            elif card.get("Card Type") in {"Artifact","Enchantment"}:
                permanent={"id":source,"tapped":False,"card_type":card.get("Card Type"),"effect":card.get("Simplified Effect","")}
                controller.battlefield.append(permanent); changes.append({"type":"ENTER_BATTLEFIELD","card_id":source})
                if "enchant creature" in effect and targets:
                    _,target_perm=self._find_permanent(targets[0])
                    if target_perm: target_perm["pacifism"]=True; permanent["enchanted_target"]=targets[0]
            elif "can't gain life" in effect and controller:
                for p in self.state.players.values(): p.life_gain_prevented=True
                changes.append({"type":"LIFE_GAIN_PREVENTION","target":"ALL"})
            elif "can't be prevented" in effect:
                for p in self.state.players.values(): p.damage_prevented=True
                changes.append({"type":"DAMAGE_PREVENTION","target":"ALL"})
            elif "gets +4/+4" in effect and targets:
                _,perm=self._find_permanent(targets[0]);
                if perm: perm["temp_power"]=perm.get("temp_power",0)+4; perm["temp_toughness"]=perm.get("temp_toughness",0)+4; changes.append({"type":"PUMP","target":targets[0],"power":4,"toughness":4})
            elif "gets +1/+0" in effect and targets:
                _,perm=self._find_permanent(targets[0]);
                if perm: perm["temp_power"]=perm.get("temp_power",0)+1; changes.append({"type":"PUMP","target":targets[0],"power":1,"toughness":0})
            elif "gets +3/+3" in effect and targets:
                _,perm=self._find_permanent(targets[0]);
                if perm: perm["temp_power"]=perm.get("temp_power",0)+3; perm["temp_toughness"]=perm.get("temp_toughness",0)+3; changes.append({"type":"PUMP","target":targets[0],"power":3,"toughness":3})
        if card.get("Card Type") not in {"Creature","Artifact Creature","Enchantment","Artifact"} and result=="RESOLVED":
            controller.graveyard.append({"id":source,"card":card})
        elif result=="FIZZLE" and controller and card.get("Card Type") not in {"Creature","Artifact Creature"}:
            controller.graveyard.append({"id":source,"card":card})
        return {"result":result,"stack_item_id":item.get("stack_item_id"),"state_changes":changes}

    def _fire_triggers(self, event, source_id, permanent):
        # Deterministic subset of the fixed card set.
        base=source_id.rsplit("_",1)[0]
        if event=="ETB" and base=="gray_merchant":
            self._stack_counter += 1
            self.state.stack.append({"stack_item_id":f"trg_{self._stack_counter:03d}","item_type":"TRIGGER_ABILITY","source_id":source_id,"controller_id":self.state.active_player,"targets":[],"trigger_effect":"GRAY_MERCHANT_ETB"})
        if event=="ETB" and base=="gravedigger":
            self._stack_counter+=1
            trigger_id=f"trg_{self._stack_counter:03d}"
            controller_id=self.state.active_player
            legal=[entry.get("id") for entry in self.state.players[controller_id].graveyard if isinstance(entry,dict) and entry.get("id")]
            if legal:
                self.state.pending_trigger_choices[controller_id]={"trigger_id":trigger_id,"item":{"stack_item_id":trigger_id,"item_type":"TRIGGER_ABILITY","source_id":source_id,"controller_id":controller_id,"targets":[],"trigger_effect":"GRAVEDIGGER_ETB"},"requires_target":True,"legal_targets":legal,"effect_summary":"Return target creature card from your graveyard to your hand."}
=======
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
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108

    def _check_state_based_actions(self):
        for player_id, player in self.state.players.items():
            if player.life <= 0:
<<<<<<< HEAD
                self.state.game_over=True; self.state.winner=next((pid for pid in self.state.players if pid!=player_id),None); self.state.game_over_reason="LIFE_ZERO"; self.state.priority_player=None; return
        for player in self.state.players.values():
            keep=[]
            for permanent in player.battlefield:
                if "toughness" in permanent and (permanent.get("toughness",0)<=0 or permanent.get("damage",0)>=permanent.get("toughness",1)):
                    player.graveyard.append(permanent)
                else: keep.append(permanent)
            player.battlefield=keep
=======
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
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108

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

<<<<<<< HEAD
    def activate_ability(self, player_id: str, source_id: str, ability_index: int, targets: list, cost_payment: dict):
        if self.state.game_over: raise ValueError("Cannot act after game over")
        if self.state.priority_player != player_id: raise ValueError("NOT_PRIORITY_PLAYER")
        player=self.state.players.get(player_id)
        if not player: raise ValueError("NOT_IN_GAME")
        owner, source=self._find_permanent(source_id)
        if owner != player_id or source is None: raise ValueError("ILLEGAL_ACTION")
        card=self.cards.get_by_instance_id(source_id)
        if card is None: raise ValueError("ILLEGAL_ACTION")
        effects=[x.strip() for x in card.get("Simplified Effect","").split(".") if x.strip()]
        if ability_index < 0 or ability_index >= len(effects): raise ValueError("ILLEGAL_ACTION")
        ability=effects[ability_index].lower()
        payment=cost_payment or {}
        # Validate explicit activation costs encoded in the fixed card effect.
        symbols=re.findall(r"\{([WUBRGC0-9]+)\}", ability.upper())
        required={c:0 for c in "WUBRG"}; generic_required=0
        for sym in symbols:
            if sym in required: required[sym]+=1
            elif sym.isdigit(): generic_required+=int(sym)
        supplied={k.upper():int(v) for k,v in (payment.get("mana",{}) or {}).items()}
        for c in "WUBRG":
            if supplied.get(c,0)<required[c]: raise ValueError("INSUFFICIENT_MANA")
        generic=supplied.get("C",0)
        if generic < generic_required: raise ValueError("INSUFFICIENT_MANA")
        if payment.get("tap"):
            if source.get("tapped"): raise ValueError("ILLEGAL_ACTION")
            source["tapped"]=True
        # Consume activation mana costs. Mana abilities with no mana cost remain free.
        for c in "WUBRG":
            need=required[c]
            pool=min(need,player.mana_pool.get(c,0)); player.mana_pool[c]-=pool; need-=pool
            if need:
                self._tap_mana_sources(player,c,need)
        need=generic_required
        pool_generic=min(need,player.mana_pool.get("C",0)); player.mana_pool["C"]-=pool_generic; need-=pool_generic
        if need:
            srcs=self._untapped_mana_sources(player)
            if len(srcs)<need: raise ValueError("INSUFFICIENT_MANA")
            for src in srcs[:need]: src["tapped"]=True
        # Mana abilities resolve immediately and do not use the stack.
        if "add {" in ability:
            if "{c}{c}" in ability: player.mana_pool["C"]+=2
            else:
                color=next((c for c in "WUBRG" if "{"+c.lower()+"}" in ability),None)
                if color: player.mana_pool[color]+=1
            self.state.consecutive_passes=0
            self.grant_priority(player_id)
            return {"type":"ABILITY_ACTIVATED","resolved_immediately":True,"source":source_id,"priority_player":player_id,"priority_seq_num":self.state.priority_seq_num}
        if "tap: draw" in ability and not player.library:
            raise ValueError("DECK_EMPTY")
        self._validate_targets(card, targets)
        self._stack_counter+=1; sid=f"stk_{self._stack_counter:03d}"
        item={"stack_item_id":sid,"item_type":"ABILITY","source_id":source_id,"controller_id":player_id,"targets":list(targets),"ability_effect":ability,"card":card}
        self.push_stack(item); self.state.consecutive_passes=0; self.grant_priority(player_id)
        return {"type":"ABILITY_ACTIVATED","stack_item_id":sid,"item_type":"ABILITY","source":source_id,"targets":list(targets),"controller":player_id,"priority_player":player_id,"priority_seq_num":self.state.priority_seq_num}

    def discard(self, player_id: str, card_ids: list):
        if self.state.phase != "CLEANUP": raise ValueError("WRONG_PHASE")
        player=self.state.players.get(player_id)
        if not player or len(player.hand)<=7: raise ValueError("ILLEGAL_ACTION")
        if not isinstance(card_ids,list) or len(card_ids)!=len(player.hand)-7 or len(set(card_ids))!=len(card_ids): raise ValueError("ILLEGAL_ACTION")
        for cid in card_ids:
            if cid not in player.hand: raise ValueError("ILLEGAL_ACTION")
        for cid in card_ids:
            player.hand.remove(cid); player.graveyard.append({"id":cid,"card":self.cards.get_by_instance_id(cid)})
        self.state.pending_discard_seq.pop(player_id,None)
        return {"player_id":player_id,"discarded":list(card_ids)}

    def concede(self, player_id: str):
        if player_id not in self.state.players: raise ValueError("NOT_IN_GAME")
        self.state.game_over=True; self.state.winner=next((pid for pid in self.state.players if pid!=player_id),None); self.state.game_over_reason="CONCEDE"; self.state.priority_player=None
        return {"winner_id":self.state.winner,"loser_id":player_id,"reason":"CONCEDE"}

=======
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108
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

    def declare_attackers(self, player_id: str, attackers: list):
        result=self.combat.declare_attackers(player_id, attackers)
        if result is None and any(a.get("creature_id","").rsplit("_",1)[0]=="goblin_guide" for a in attackers):
            self._stack_counter+=1
            self.state.stack.append({"stack_item_id":f"trg_{self._stack_counter:03d}","item_type":"TRIGGER_ABILITY","source_id":next(a["creature_id"] for a in attackers if a.get("creature_id","").rsplit("_",1)[0]=="goblin_guide"),"controller_id":player_id,"targets":[],"trigger_effect":"GOBLIN_GUIDE_ATTACK"})
        return result

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
    def resolve_combat_damage(self, first_strike=False):
        self._stack_counter += 1
        return self.combat.resolve_combat(self._stack_counter, first_strike=first_strike)

    def assign_damage_order(self, player_id: str, attacker_id: str, blocker_order: list):
        return self.combat.assign_damage_order(player_id, attacker_id, blocker_order)
