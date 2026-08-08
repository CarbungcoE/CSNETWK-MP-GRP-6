class combatsystem:
    def __init__(self, gstate):
        self.gstate = gstate
        self.clear_combat()

    def clear_combat(self):
        self.atks = []
        self.blks = []
        self.atk_order = {}

    def declare_attackers(self, pid, atk_input):
        if pid != self.gstate["active_player"]:
            return "Active player must declare attackers."

        ap_board = self.gstate["battlefield"].get(pid, [])
        ap_cards = {c["id"]: c for c in ap_board if "power" in c}

        for entry in atk_input:
            cid = entry.get("creature_id")
            if cid not in ap_cards:
                return f"{cid} not found on active player's battlefield."
            
            unit = ap_cards[cid]
            if unit.get("tapped", False):
                return f"{cid} is tapped."
            
            if unit.get("summoning_sickness", False) and not unit.get("haste", False):
                return f"{cid} has summoning sickness."

        for entry in atk_input:
            cid = entry["creature_id"]
            ap_cards[cid]["tapped"] = True

        self.atks = atk_input
        return None

    def declare_blockers(self, pid, blk_input):
        if pid == self.gstate["active_player"]:
            return "Defender must declare blockers."

        nap_board = self.gstate["battlefield"].get(pid, [])
        nap_cards = {c["id"]: c for c in nap_board if "power" in c}
        valid_targets = {a["creature_id"] for a in self.atks}
        used_guarders = set()

        for entry in blk_input:
            cid = entry.get("creature_id")
            target_atk = entry.get("blocking_id")

            if cid not in nap_cards:
                return f"{cid} not found on defender's board."
            if target_atk not in valid_targets:
                return f"{target_atk} is not an active attacker."
            if cid in used_guarders:
                return f"{cid} assigned twice."
            if nap_cards[cid].get("tapped", False):
                return f"{cid} is tapped."

            used_guarders.add(cid)

        self.blks = blk_input
        return None

    def check_damage_order_needed(self):
        blk_counts = {}
        for b in self.blks:
            target = b["blocking_id"]
            blk_counts.setdefault(target, []).append(b["creature_id"])
        return [target for target, guards in blk_counts.items() if len(guards) >= 2]

    def resolve_combat(self, seq_num):
        ap = self.gstate["active_player"]
        nap = self.gstate["non_active_player"]

        ap_board = {c["id"]: c for c in self.gstate["battlefield"].get(ap, [])}
        nap_board = {c["id"]: c for c in self.gstate["battlefield"].get(nap, [])}

        atk_to_blks = {}
        for b in self.blks:
            atk_to_blks.setdefault(b["blocking_id"], []).append(b["creature_id"])

        dmg_logs = []
        dead_units = []

        for a in self.atks:
            aid = a["creature_id"]
            atk_card = ap_board.get(aid)
            if not atk_card:
                continue

            pwr = atk_card.get("power", 0)
            assigned_blks = atk_to_blks.get(aid, [])

            if not assigned_blks:
                dmg_logs.append({
                    "source": aid,
                    "target": nap,
                    "amount": pwr
                })
                self.gstate["life_totals"][nap] -= pwr
            else:
                chosen_seq = self.atk_order.get(aid, assigned_blks)
                rem_pwr = pwr

                for bid in chosen_seq:
                    blk_card = nap_board.get(bid)
                    if not blk_card or rem_pwr <= 0:
                        break
                    
                    hit = min(rem_pwr, blk_card.get("toughness", 0) - blk_card.get("damage", 0))
                    if hit == 0 and rem_pwr > 0:
                        hit = rem_pwr

                    blk_card["damage"] = blk_card.get("damage", 0) + hit
                    rem_pwr -= hit

                    dmg_logs.append({
                        "source": aid,
                        "target": bid,
                        "amount": hit
                    })

        for b in self.blks:
            bid = b["creature_id"]
            aid = b["blocking_id"]
            blk_card = nap_board.get(bid)
            atk_card = ap_board.get(aid)

            if blk_card and atk_card:
                pwr = blk_card.get("power", 0)
                if pwr > 0:
                    atk_card["damage"] = atk_card.get("damage", 0) + pwr
                    dmg_logs.append({
                        "source": bid,
                        "target": aid,
                        "amount": pwr
                    })

        for player_id in [ap, nap]:
            surviving = []
            for item in self.gstate["battlefield"][player_id]:
                if "power" in item:
                    if item.get("damage", 0) >= item.get("toughness", 1):
                        dead_units.append(item["id"])
                        self.gstate["graveyard"][player_id].append(item)
                    else:
                        surviving.append(item)
                else:
                    surviving.append(item)
            self.gstate["battlefield"][player_id] = surviving

        return {
            "type": "COMBAT_DAMAGE_RESULT",
            "seq_num": seq_num,
            "damage_events": dmg_logs,
            "life_totals": self.gstate["life_totals"].copy(),
            "creatures_died": dead_units
        }