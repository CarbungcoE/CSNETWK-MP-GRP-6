from mtgnp.game.game_state import GameState
from mtgnp.game.player import PlayerState
from mtgnp.game.turn import TurnEngine


def make_state():
    state = GameState(phase="MULLIGAN")
    state.players = {
        "player_1": PlayerState("player_1", deck=["mountain_001"]),
        "player_2": PlayerState("player_2", deck=["mountain_002"]),
    }
    state.active_player = "player_1"
    return state


state = make_state()
engine = TurnEngine(state)

transitions = engine.start_game()
assert state.turn == 1
assert state.phase == "UNTAP"
assert transitions == [{"from_phase": "MULLIGAN", "to_phase": "UNTAP"}]

# First turn: no draw.
state.players["player_1"].hand = ["mountain_001"]
state.players["player_1"].library = ["mountain_002"]
engine.advance_phase()
assert state.phase == "UPKEEP"
engine.advance_phase()
assert state.phase == "DRAW"
assert state.players["player_1"].hand == ["mountain_001"]
assert state.players["player_1"].library == ["mountain_002"]

# Advance to main; automatic phases should not mutate the hand.
engine.advance_phase()
assert state.phase == "PRECOMBAT_MAIN"

# Verify a second turn untaps and draws.
state.players["player_1"].battlefield = [{"id": "mountain_001", "tapped": True}]
state.players["player_1"].library = ["mountain_003"]
state.players["player_1"].hand = []
state.players["player_2"].library = ["mountain_004"]
state.players["player_2"].hand = []
state.active_player = "player_1"
state.phase = "CLEANUP"
engine.advance_phase()
assert state.turn == 2
assert state.active_player == "player_2"
assert state.phase == "UNTAP"
engine.advance_phase()
assert state.phase == "UPKEEP"
engine.advance_phase()
assert state.phase == "DRAW"
assert state.players["player_2"].hand == ["mountain_004"]
assert state.players["player_2"].library == []

print("TURN_ENGINE milestone passed")
