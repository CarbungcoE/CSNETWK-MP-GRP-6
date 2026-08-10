import random
from typing import Dict, Any, Tuple

from .game_state import GameState
from .player import PlayerState
from .card_catalog import CardCatalog


class GameLifecycle:
    """
    Manages the LOBBY, GAME_SETUP, and MULLIGAN states
    of the MTGNP server.
    """

    def __init__(self, state: GameState):
        self.state = state
        self.cards = CardCatalog()

    def process_player_ready(
        self,
        player_id: str,
        deck_list: list,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Handles a PLAYER_READY PDU.

        Returns:
            (success_bool, error_code, state_dict)
        """
        if self.state.phase != "LOBBY":
            return False, "WRONG_PHASE", {}

        if not player_id:
            return False, "INVALID_PLAYER_ID", {}

        # Exactly two players are allowed in a game.
        if (
            player_id not in self.state.players
            and len(self.state.players) >= 2
        ):
            return False, "GAME_FULL", {}

        # Validate deck size and every card instance against the
        # authoritative fixed card list.
        if not isinstance(deck_list, list) or not (1 <= len(deck_list) <= 50):
            return False, "ILLEGAL_DECK", {}
        if any(not self.cards.is_known_instance(card_id) for card_id in deck_list):
<<<<<<< HEAD
            return False, "ILLEGAL_DECK", {}
        # Instance IDs are unique physical cards; base-copy limits come from the master list.
        counts={}
        for card_id in deck_list:
            base=card_id.rsplit("_",1)[0]
            counts[base]=counts.get(base,0)+1
            card=self.cards.get(base)
            if card and counts[base] > int(card.get("Copies in Set") or 999):
                return False, "ILLEGAL_DECK", {}
        if len(set(deck_list)) != len(deck_list):
=======
>>>>>>> 5b145c627681b7093f9eab1d74ae9ddf22b34108
            return False, "ILLEGAL_DECK", {}

        # Register or update player.
        self.state.players[player_id] = PlayerState(
            player_id=player_id,
            deck=list(deck_list),
        )

        # The second ready player starts automated setup.
        if len(self.state.players) == 2:
            self.setup_game()

            return True, "", {
                "phase": self.state.phase,
                "active_player": self.state.active_player,
            }

        # Still waiting for the second player.
        lobby_state = {
            "phase": "LOBBY",
            "players_ready": len(self.state.players),
            "waiting_for": ["PLAYER"],
        }

        return True, "", lobby_state

    def setup_game(self) -> None:
        """
        Execute GAME_SETUP automated steps and transition
        to MULLIGAN.
        """
        if len(self.state.players) != 2:
            raise ValueError(
                "GAME_SETUP requires exactly two players."
            )

        self.state.phase = "GAME_SETUP"
        self.state.turn = 0
        self.state.game_over = False
        self.state.winner = None
        self.state.game_over_reason = None

        self.state.priority_player = None
        self.state.priority_seq_num = 0
        self.state.stack.clear()
        self.state.phase_action_seq = 0
        self.state.phase_decision_complete = False
        self.state.pending_discard_seq.clear()
        self.state.pending_trigger_orders.clear()
        self.state.pending_trigger_choices.clear()
        self.state.pending_trigger_choice_seq.clear()
        self.state.pending_trigger_order_seq.clear()

        # Determine who goes first.
        self.state.active_player = random.choice(
            list(self.state.players.keys())
        )

        for player in self.state.players.values():
            # Initialize life and library.
            player.life = 20
            player.library = list(player.deck)
            random.shuffle(player.library)

            # Reset zones and per-game state.
            player.hand.clear()
            player.battlefield.clear()
            player.graveyard.clear()

            player.mulligan_count = 0
            player.kept_hand = False
            player.land_played_this_turn = False
            player.exile.clear()
            player.mana_pool = {c: 0 for c in "WUBRGC"}
            player.damage_prevention = 0
            player.life_gain_prevented = False
            player.damage_prevented = False

            # Draw initial seven cards.
            draw_count = min(
                7,
                len(player.library),
            )

            player.hand = [
                player.library.pop()
                for _ in range(draw_count)
            ]

        self.state.phase = "MULLIGAN"

    def process_mulligan(
        self,
        player_id: str,
        keep: bool,
        cards_to_bottom: list,
    ) -> Tuple[bool, str]:
        """
        Handles a MULLIGAN_CHOICE PDU.

        Returns:
            (success_bool, error_code)
        """
        if self.state.phase != "MULLIGAN":
            return False, "WRONG_PHASE"

        player = self.state.players.get(player_id)

        if player is None:
            return False, "ILLEGAL_ACTION"

        if player.kept_hand:
            return False, "ILLEGAL_ACTION"

        if not isinstance(cards_to_bottom, list):
            return False, "ILLEGAL_ACTION"

        if not keep:
            # A player choosing to mulligan should not submit
            # cards to bottom at the same time.
            if cards_to_bottom:
                return False, "ILLEGAL_ACTION"

            player.mulligan_count += 1

            # Return the hand to the library and shuffle.
            player.library.extend(player.hand)
            player.hand.clear()

            random.shuffle(player.library)

            # Draw a fresh opening hand.
            draw_count = min(
                7,
                len(player.library),
            )

            player.hand = [
                player.library.pop()
                for _ in range(draw_count)
            ]

        else:
            # London Mulligan:
            # the player must bottom exactly as many cards
            # as their number of previous mulligans.
            if len(cards_to_bottom) != player.mulligan_count:
                return False, "ILLEGAL_ACTION"

            # Validate everything before modifying the hand.
            hand_copy = list(player.hand)

            for card in cards_to_bottom:
                if card not in hand_copy:
                    return False, "ILLEGAL_ACTION"

                hand_copy.remove(card)

            # Move selected cards to the bottom of the library.
            for card in cards_to_bottom:
                player.hand.remove(card)
                player.library.insert(0, card)

            player.kept_hand = True

        return True, ""

    def is_mulligan_complete(self) -> bool:
        """
        Check whether both players have kept their hands.
        """
        if len(self.state.players) != 2:
            return False

        return all(
            player.kept_hand
            for player in self.state.players.values()
        )

    def start_game(self) -> None:
        """
        Transition from MULLIGAN into the first turn.

        Turn progression itself is delegated to TurnEngine
        through GameSession.
        """
        if self.state.phase != "MULLIGAN":
            raise ValueError(
                f"Cannot start game from phase {self.state.phase}"
            )

        if not self.is_mulligan_complete():
            raise ValueError(
                "Cannot start game before all players keep their hands"
            )

        # The actual first-turn initialization is performed
        # by TurnEngine through GameSession.
        self.state.phase = "UNTAP"
        self.state.turn = 1

    def generate_visible_state(
        self,
        target_player_id: str,
    ) -> Dict[str, Any]:
        """
        Generate the authoritative state visible to a specific player.

        A player's hand is visible only to that player.
        """
        if target_player_id not in self.state.players:
            raise ValueError(
                f"Unknown player: {target_player_id}"
            )

        target_player = self.state.players[
            target_player_id
        ]

        return {
            "turn": self.state.turn,
            "phase": self.state.phase,
            "active_player": self.state.active_player,
            "priority_player": self.state.priority_player,
            "priority_seq_num": self.state.priority_seq_num,
            "land_played_this_turn": target_player.land_played_this_turn,
            "life_totals": {
                pid: player.life
                for pid, player in self.state.players.items()
            },
            "hand": list(target_player.hand),
            "hand_counts": {
                pid: len(player.hand)
                for pid, player in self.state.players.items()
            },
            "library_counts": {
                pid: len(player.library)
                for pid, player in self.state.players.items()
            },
            "battlefield": {
                pid: list(player.battlefield)
                for pid, player in self.state.players.items()
            },
            "graveyard": {
                pid: list(player.graveyard)
                for pid, player in self.state.players.items()
            },
            "stack": list(self.state.stack),
        }