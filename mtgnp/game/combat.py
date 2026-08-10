from mtgnp.game.game_state import GameState


class CombatSystem:
    """Authoritative combat declarations and damage resolution."""

    def __init__(self, state: GameState):
        self.state = state
        self.clear_combat()

    def clear_combat(self):
        self.atks = []
        self.blks = []
        self.atk_order = {}
        self.first_strike_resolved = False

    def _get_non_active_player(self):
        return next((pid for pid in self.state.players if pid != self.state.active_player), None)

    def _creatures(self, pid):
        return {c["id"]: c for c in self.state.players[pid].battlefield if "power" in c}

    def declare_attackers(self, pid, atk_input):
        if self.state.phase != "DECLARE_ATTACKERS":
            return "WRONG_PHASE"
        if pid != self.state.active_player:
            return "NOT_ACTIVE_PLAYER"
        if self.state.phase_decision_complete:
            return "ILLEGAL_ACTION"
        if not isinstance(atk_input, list):
            return "ILLEGAL_ACTION"
        cards = self._creatures(pid)
        seen = set()
        for entry in atk_input:
            if not isinstance(entry, dict):
                return "ILLEGAL_ACTION"
            cid = entry.get("creature_id")
            target = entry.get("target", self._get_non_active_player())
            if cid in seen or cid not in cards:
                return "ILLEGAL_ACTION"
            if target != self._get_non_active_player():
                return "ILLEGAL_TARGET"
            seen.add(cid)
            c = cards[cid]
            if c.get("tapped"):
                return "ILLEGAL_ACTION"
            if c.get("summoning_sickness") and not c.get("haste"):
                return "ILLEGAL_ACTION"
            if c.get("defender"):
                return "ILLEGAL_ACTION"
            if c.get("pacifism"):
                return "ILLEGAL_ACTION"
        for cid in seen:
            cards[cid]["tapped"] = True
            cards[cid]["attacking"] = True
        self.atks = list(atk_input)
        for entry in self.atks:
            if entry["creature_id"].rsplit("_",1)[0] == "goblin_guide":
                if hasattr(self.state, "pending_trigger_orders"):
                    # Trigger is represented on the stack immediately; it will resolve through GameSession.
                    self.state._goblin_guide_trigger = entry["creature_id"]
        self.blks = []
        self.atk_order = {}
        self.state.phase_decision_complete = True
        return None

    def _find_card_any(self, cid):
        for pid,p in self.state.players.items():
            for c in p.battlefield:
                if c.get("id")==cid: return pid,c
        return None,None

    def declare_blockers(self, pid, blk_input):
        if self.state.phase != "DECLARE_BLOCKERS":
            return "WRONG_PHASE"
        if pid == self.state.active_player:
            return "NOT_NON_ACTIVE_PLAYER"
        if self.state.phase_decision_complete:
            return "ILLEGAL_ACTION"
        if not isinstance(blk_input, list):
            return "ILLEGAL_ACTION"
        cards = self._creatures(pid)
        attackers = {a["creature_id"] for a in self.atks}
        used = set()
        for entry in blk_input:
            if not isinstance(entry, dict):
                return "ILLEGAL_ACTION"
            cid = entry.get("creature_id"); aid = entry.get("blocking_id")
            if cid in used or cid not in cards or aid not in attackers:
                return "ILLEGAL_ACTION"
            if cards[cid].get("tapped") or cards[cid].get("summoning_sickness"):
                return "ILLEGAL_ACTION"
            if cards[cid].get("pacifism"):
                return "ILLEGAL_ACTION"
            atk = next((x for x in self.atks if x["creature_id"] == aid), None)
            if atk:
                _, atk_card = self._find_card_any(aid)
                if atk_card and atk_card.get("flying") and not (cards[cid].get("flying") or cards[cid].get("reach")):
                    return "ILLEGAL_ACTION"
            used.add(cid)
        self.blks = list(blk_input)
        self.atk_order = {}
        self.state.phase_decision_complete = True
        return None

    def check_damage_order_needed(self):
        counts = {}
        for b in self.blks:
            counts.setdefault(b["blocking_id"], []).append(b["creature_id"])
        return [aid for aid, blockers in counts.items() if len(blockers) > 1]

    def assign_damage_order(self, pid, attacker_id, blocker_order):
        if self.state.phase != "ASSIGN_DAMAGE_ORDER":
            raise ValueError("WRONG_PHASE")
        if pid != self.state.active_player:
            raise ValueError("NOT_ACTIVE_PLAYER")
        needed = set(self.check_damage_order_needed())
        if attacker_id not in needed:
            raise ValueError("ILLEGAL_ACTION")
        assigned = [b["creature_id"] for b in self.blks if b["blocking_id"] == attacker_id]
        if not isinstance(blocker_order, list) or set(blocker_order) != set(assigned) or len(blocker_order) != len(assigned):
            raise ValueError("ILLEGAL_ACTION")
        self.atk_order[attacker_id] = list(blocker_order)
        return {"attacker_id": attacker_id, "blocker_order": list(blocker_order)}

    def _apply_damage(self, source, target, amount, logs):
        if amount <= 0:
            return
        if target in self.state.players:
            player = self.state.players[target]
            prevented = min(amount, player.damage_prevention)
            player.damage_prevention -= prevented
            amount -= prevented
            if amount:
                player.life -= amount
            if amount:
                logs.append({"source": source, "target": target, "amount": amount})
        else:
            for player in self.state.players.values():
                for c in player.battlefield:
                    if c.get("id") == target:
                        c["damage"] = c.get("damage", 0) + amount
                        logs.append({"source": source, "target": target, "amount": amount})
                        return

    def _remove_lethal(self):
        died=[]
        for player in self.state.players.values():
            keep=[]
            for c in player.battlefield:
                if "toughness" in c and (c.get("toughness", 0) <= 0 or c.get("damage", 0) >= c.get("toughness", 1)):
                    died.append(c["id"])
                    player.graveyard.append(c)
                else:
                    keep.append(c)
            player.battlefield=keep
        return died

    def resolve_combat(self, seq_num, first_strike=False):
        ap=self.state.active_player; nap=self._get_non_active_player()
        if not ap or not nap: raise ValueError("Cannot resolve combat without two players")
        ap_cards=self._creatures(ap); nap_cards=self._creatures(nap)
        logs=[]; dealt=[]
        order={aid:self.atk_order.get(aid,[b["creature_id"] for b in self.blks if b["blocking_id"]==aid]) for aid in [a["creature_id"] for a in self.atks]}
        blocking_by={b["creature_id"]:b["blocking_id"] for b in self.blks}
        for a in self.atks:
            aid=a["creature_id"]; atk=ap_cards.get(aid)
            if not atk: continue
            has_fs=atk.get("first_strike") or atk.get("double_strike")
            if first_strike != bool(has_fs): continue
            blockers=order.get(aid,[])
            if not blockers:
                self._apply_damage(aid,nap,atk.get("power",0)+atk.get("temp_power",0),logs)
            else:
                rem=atk.get("power",0)+atk.get("temp_power",0)
                for bid in blockers:
                    b=nap_cards.get(bid)
                    if not b or rem<=0: continue
                    lethal=max(0,b.get("toughness",0)+b.get("temp_toughness",0)-b.get("damage",0))
                    hit=min(rem,lethal)
                    self._apply_damage(aid,bid,hit,logs); rem-=hit
        for b in self.blks:
            bid=b["creature_id"]; aid=b["blocking_id"]; blk=nap_cards.get(bid); atk=ap_cards.get(aid)
            if not blk or not atk: continue
            has_fs=blk.get("first_strike") or blk.get("double_strike")
            if first_strike != bool(has_fs): continue
            self._apply_damage(bid,aid,blk.get("power",0)+blk.get("temp_power",0),logs)
        died=self._remove_lethal()
        return {"type":"COMBAT_DAMAGE_RESULT","seq_num":seq_num,"damage_events":logs,"life_totals":{pid:p.life for pid,p in self.state.players.items()},"creatures_died":died,"first_strike":first_strike}
