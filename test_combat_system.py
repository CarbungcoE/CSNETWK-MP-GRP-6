from mtgnp.server.game_session import GameSession


def creature(cid, power, toughness, **flags):
    return {
        "id": cid, "power": power, "toughness": toughness, "damage": 0,
        "tapped": False, "summoning_sickness": False, "haste": True,
        "first_strike": False, "double_strike": False, "flying": False,
        "defender": False, "trample": False, "hexproof": False, **flags,
    }


s = GameSession()
deck = ["mountain_001", "goblin_guide_001", "mountain_002"]
s.player_ready("player_1", deck)
s.player_ready("player_2", deck)
for player in s.state.players.values():
    player.kept_hand = True

s.state.active_player = "player_1"
s.state.phase = "DECLARE_ATTACKERS"
s.state.players["player_1"].battlefield = [creature("goblin_guide_001", 2, 2)]
s.state.players["player_2"].battlefield = []

assert s.declare_attackers("player_1", [{"creature_id": "goblin_guide_001", "target": "player_2"}]) is None
assert s.combat.atks

# The active player receives priority after declaring attackers.
s.grant_active_player_priority()

# Resolve the Goblin Guide trigger, then pass the declaration priority window.
s.pass_priority()
s.pass_priority()
s.pass_priority()
s.pass_priority()

assert s.state.phase == "DECLARE_BLOCKERS"
assert s.declare_blockers("player_2", []) is None
s.grant_active_player_priority()
s.pass_priority()
result = s.pass_priority()

assert result["combat_results"]
assert s.state.players["player_2"].life == 18
assert s.state.phase == "END_OF_COMBAT"

print("COMBAT_SYSTEM milestone passed")
