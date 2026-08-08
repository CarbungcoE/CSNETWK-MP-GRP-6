import random
from typing import Dict, Any, Tuple

class GameLifecycleManager:
    """Manages the LOBBY, GAME_SETUP, and MULLIGAN states of the MTGNP server."""
    
    def __init__(self):
        self.current_phase = "LOBBY"
        self.players = {}  # maps player_id into dict of game state (deck, hand, library, life, etc.)
        self.active_player = None
        self.turn = 0

    def process_player_ready(self, player_id: str, deck_list: list) -> Tuple[bool, str, Dict[str, Any]]:
        """Handles a PLAYER_READY PDU. Returns (success_bool, error_code, lobby_state_dict)."""
        if self.current_phase != "LOBBY":
            return False, "WRONG_PHASE", {}

        # validate deck size (1 to 50 cards per RFC)
        if not (1 <= len(deck_list) <= 50):
            return False, "ILLEGAL_DECK", {}

        # register or update player
        self.players[player_id] = {
            "deck": deck_list,
            "library": [],
            "hand": [],
            "life": 20,
            "mulligan_count": 0,
            "kept_hand": False
        }

        # build LOBBY phase GAME_STATE_UPDATE
        waiting_for = [pid for pid in ["player_1", "player_2"] if pid not in self.players]
        lobby_state = {
            "phase": "LOBBY",
            "players_ready": len(self.players),
            "waiting_for": waiting_for
        }
        
        return True, "", lobby_state

    def setup_game(self):
        """Executes GAME_SETUP automated steps and transitions to MULLIGAN."""
        self.current_phase = "MULLIGAN"
        self.turn = 0
        
        # determine who goes first via random coin flip
        self.active_player = random.choice(list(self.players.keys()))
        
        for pid, pdata in self.players.items():
            # initialize life and library
            pdata["life"] = 20
            pdata["library"] = pdata["deck"].copy()
            random.shuffle(pdata["library"])
            
            # draw initial 7 cards
            pdata["hand"] = [pdata["library"].pop() for _ in range(min(7, len(pdata["library"])))]

    def process_mulligan(self, player_id: str, keep: bool, cards_to_bottom: list) -> Tuple[bool, str]:
        """Handles a MULLIGAN_CHOICE PDU. Returns (success_bool, error_code)."""
        if self.current_phase != "MULLIGAN":
            return False, "WRONG_PHASE"

        pdata = self.players[player_id]

        if keep:
            # London Mulligan validation: must bottom exactly 'mulligan_count' cards
            if len(cards_to_bottom) != pdata["mulligan_count"]:
                return False, "ILLEGAL_ACTION"
            
            # Process bottoming
            for card in cards_to_bottom:
                if card in pdata["hand"]:
                    pdata["hand"].remove(card)
                    pdata["library"].insert(0, card)  # index 0 is the bottom
                else:
                    return False, "ILLEGAL_ACTION" # card wasn't in hand
            
            pdata["kept_hand"] = True
        else:
            # player mulligans: shuffle hand back and draw 7
            pdata["mulligan_count"] += 1
            pdata["library"].extend(pdata["hand"])
            pdata["hand"].clear()
            random.shuffle(pdata["library"])
            
            # Redraw
            pdata["hand"] = [pdata["library"].pop() for _ in range(min(7, len(pdata["library"])))]

        return True, ""

    def is_mulligan_complete(self) -> bool:
        """Checks if both players have kept their hands."""
        if len(self.players) < 2:
            return False
        return all(pdata.get("kept_hand", False) for pdata in self.players.values())

    def generate_visible_state(self, target_player_id: str) -> Dict[str, Any]:
        """Generates the authoritative state dictionary, hiding the opponent's hand."""
        state = {
            "turn": self.turn,
            "phase": self.current_phase,
            "active_player": self.active_player,
            "life_totals": {pid: pdata["life"] for pid, pdata in self.players.items()},
            "hand": self.players[target_player_id]["hand"],  # only their own hand
            "hand_counts": {pid: len(pdata["hand"]) for pid, pdata in self.players.items()},
            "library_counts": {pid: len(pdata["library"]) for pid, pdata in self.players.items()},
            "battlefield": {"player_1": [], "player_2": []},
            "graveyard": {"player_1": [], "player_2": []},
            "stack": []
        }
        return state