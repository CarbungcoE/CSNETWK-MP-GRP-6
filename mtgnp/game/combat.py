from mtgnp.game.game_state import GameState


class CombatSystem:
    """
    Manages combat for the active game.

    CombatSystem does not own game state. It operates on the
    authoritative GameState supplied by GameSession.
    """

    def __init__(self, state: GameState):
        self.state = state
        self.clear_combat()

    def clear_combat(self):
        """
        Clear all combat assignments and damage-order information.
        """
        self.atks = []
        self.blks = []
        self.atk_order = {}

    def _get_non_active_player(self) -> str | None:
        """
        Return the player who is not currently active.
        """
        player_ids = list(self.state.players.keys())

        if self.state.active_player not in player_ids:
            return None

        for player_id in player_ids:
            if player_id != self.state.active_player:
                return player_id

        return None

    def declare_attackers(self, pid, atk_input):
        """
        Declare attackers for the active player.
        """
        if pid != self.state.active_player:
            return "Active player must declare attackers."

        ap_player = self.state.players.get(pid)

        if ap_player is None:
            return f"{pid} is not a registered player."

        ap_board = ap_player.battlefield
        ap_cards = {
            c["id"]: c
            for c in ap_board
            if "power" in c
        }

        for entry in atk_input:
            cid = entry.get("creature_id")

            if cid not in ap_cards:
                return f"{cid} not found on active player's battlefield."

            unit = ap_cards[cid]

            if unit.get("tapped", False):
                return f"{cid} is tapped."

            if (
                unit.get("summoning_sickness", False)
                and not unit.get("haste", False)
            ):
                return f"{cid} has summoning sickness."

        for entry in atk_input:
            cid = entry["creature_id"]
            ap_cards[cid]["tapped"] = True

        self.atks = list(atk_input)

        return None

    def declare_blockers(self, pid, blk_input):
        """
        Declare blockers for the non-active player.
        """
        if pid == self.state.active_player:
            return "Defender must declare blockers."

        if pid not in self.state.players:
            return f"{pid} is not a registered player."

        nap_player = self.state.players[pid]

        nap_board = nap_player.battlefield
        nap_cards = {
            c["id"]: c
            for c in nap_board
            if "power" in c
        }

        valid_targets = {
            a["creature_id"]
            for a in self.atks
        }

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

        self.blks = list(blk_input)

        return None

    def check_damage_order_needed(self):
        """
        Return attackers that have multiple blockers assigned to them.
        """
        blk_counts = {}

        for b in self.blks:
            target = b["blocking_id"]

            blk_counts.setdefault(
                target,
                []
            ).append(
                b["creature_id"]
            )

        return [
            target
            for target, guards in blk_counts.items()
            if len(guards) >= 2
        ]

    def resolve_combat(self, seq_num):
        """
        Resolve combat damage and return a COMBAT_DAMAGE_RESULT.
        """
        ap = self.state.active_player
        nap = self._get_non_active_player()

        if ap is None:
            raise ValueError(
                "Cannot resolve combat without an active player."
            )

        if nap is None:
            raise ValueError(
                "Cannot resolve combat without a second player."
            )

        ap_player = self.state.players[ap]
        nap_player = self.state.players[nap]

        ap_board = {
            c["id"]: c
            for c in ap_player.battlefield
        }

        nap_board = {
            c["id"]: c
            for c in nap_player.battlefield
        }

        atk_to_blks = {}

        for b in self.blks:
            atk_to_blks.setdefault(
                b["blocking_id"],
                []
            ).append(
                b["creature_id"]
            )

        dmg_logs = []
        dead_units = []

        # Resolve attacker damage.
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

                nap_player.life -= pwr

            else:
                chosen_seq = self.atk_order.get(
                    aid,
                    assigned_blks
                )

                rem_pwr = pwr

                for bid in chosen_seq:
                    blk_card = nap_board.get(bid)

                    if not blk_card or rem_pwr <= 0:
                        break

                    hit = min(
                        rem_pwr,
                        blk_card.get("toughness", 0)
                        - blk_card.get("damage", 0)
                    )

                    if hit == 0 and rem_pwr > 0:
                        hit = rem_pwr

                    blk_card["damage"] = (
                        blk_card.get("damage", 0)
                        + hit
                    )

                    rem_pwr -= hit

                    dmg_logs.append({
                        "source": aid,
                        "target": bid,
                        "amount": hit
                    })

        # Resolve blocker damage.
        for b in self.blks:
            bid = b["creature_id"]
            aid = b["blocking_id"]

            blk_card = nap_board.get(bid)
            atk_card = ap_board.get(aid)

            if blk_card and atk_card:
                pwr = blk_card.get("power", 0)

                if pwr > 0:
                    atk_card["damage"] = (
                        atk_card.get("damage", 0)
                        + pwr
                    )

                    dmg_logs.append({
                        "source": bid,
                        "target": aid,
                        "amount": pwr
                    })

        # Move creatures that have lethal damage to their owner's graveyard.
        for player_id in [ap, nap]:
            player = self.state.players[player_id]

            surviving = []

            for item in player.battlefield:
                if "power" in item:
                    if (
                        item.get("damage", 0)
                        >= item.get("toughness", 1)
                    ):
                        dead_units.append(item["id"])
                        player.graveyard.append(item)
                    else:
                        surviving.append(item)
                else:
                    surviving.append(item)

            player.battlefield = surviving

        return {
            "type": "COMBAT_DAMAGE_RESULT",
            "seq_num": seq_num,
            "damage_events": dmg_logs,
            "life_totals": {
                pid: player.life
                for pid, player in self.state.players.items()
            },
            "creatures_died": dead_units
        }