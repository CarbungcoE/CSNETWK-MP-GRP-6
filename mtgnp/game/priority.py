from mtgnp.game.game_state import GameState


class PriorityManager:
    """
    Manages priority for the active game.

    PriorityManager does not own game state. It operates on the
    authoritative GameState supplied by GameSession.
    """

    def __init__(self, state: GameState):
        self.state = state

    def grant_priority(self, player_id: str) -> int:
        """
        Grant priority to a specific player.

        Each new priority grant receives a new sequence number.
        """
        if self.state.game_over:
            raise ValueError(
                "Cannot grant priority after game over"
            )

        if player_id not in self.state.players:
            raise ValueError(
                f"Unknown player: {player_id}"
            )

        self.state.priority_player = player_id
        self.state.priority_seq_num += 1

        return self.state.priority_seq_num

    def clear_priority(self) -> None:
        """
        Remove the current priority holder.
        """
        self.state.priority_player = None

    def has_priority(self, player_id: str) -> bool:
        """
        Return True if the specified player currently has priority.
        """
        return self.state.priority_player == player_id

    def pass_priority(self) -> str | None:
        """
        Pass priority to the next player.

        Returns the new priority holder.
        """
        if self.state.game_over:
            raise ValueError(
                "Cannot pass priority after game over"
            )

        if self.state.priority_player is None:
            raise ValueError(
                "Cannot pass priority when nobody has priority"
            )

        player_ids = list(self.state.players.keys())

        if not player_ids:
            raise ValueError(
                "Cannot pass priority without players"
            )

        if self.state.priority_player not in player_ids:
            raise ValueError(
                "Current priority holder is not registered"
            )

        current_index = player_ids.index(
            self.state.priority_player
        )

        next_index = (current_index + 1) % len(player_ids)

        self.state.priority_player = player_ids[next_index]
        self.state.priority_seq_num += 1

        return self.state.priority_player

    def grant_active_player_priority(self) -> str:
        """
        Grant priority to the active player.

        Returns the player receiving priority.
        """
        if self.state.active_player is None:
            raise ValueError(
                "Cannot grant priority without an active player"
            )

        self.grant_priority(self.state.active_player)

        return self.state.active_player
    
    def validate_seq_num(self, seq_num: int) -> bool:
        """
        Check whether a client-provided sequence number matches
        the currently active priority token.
        """
        return seq_num == self.state.priority_seq_num

    def get_priority_seq_num(self) -> int:
        """
        Return the current authoritative priority sequence number.
        """
        return self.state.priority_seq_num