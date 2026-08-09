from mtgnp.server.game_session import GameSession


class GameServer:
    """
    Manages active game sessions.

    GameServer is responsible for creating, storing, and removing
    GameSession instances. Game rules are handled by GameSession
    and the systems it owns.
    """

    def __init__(self):
        self.sessions: dict[str, GameSession] = {}
        self.player_sessions: dict[str, str] = {}

    def create_session(self, session_id: str) -> GameSession:
        """
        Create and register a new game session.
        """
        if not session_id:
            raise ValueError(
                "Session ID cannot be empty."
            )

        if session_id in self.sessions:
            raise ValueError(
                f"Session already exists: {session_id}"
            )

        session = GameSession()
        self.sessions[session_id] = session

        return session

    def get_or_create_session(
        self,
        session_id: str,
    ) -> GameSession:
        """
        Return an existing session or create a new one.
        """
        if not session_id:
            raise ValueError(
                "Session ID cannot be empty."
            )

        session = self.sessions.get(session_id)

        if session is not None:
            return session

        return self.create_session(session_id)

    def get_session(
        self,
        session_id: str,
    ) -> GameSession | None:
        """
        Return a session by ID.

        Returns None if the session does not exist.
        """
        return self.sessions.get(session_id)

    def remove_session(
        self,
        session_id: str,
    ) -> bool:
        """
        Remove a game session.

        Returns True if a session was removed.
        """
        session = self.sessions.pop(
            session_id,
            None,
        )

        if session is None:
            return False

        # Remove player-to-session mappings belonging
        # to this session.
        players_to_remove = [
            player_id
            for player_id, mapped_session_id
            in self.player_sessions.items()
            if mapped_session_id == session_id
        ]

        for player_id in players_to_remove:
            del self.player_sessions[player_id]

        return True

    def join_session(
        self,
        session_id: str,
        player_id: str,
    ) -> GameSession:
        """
        Associate a player with an existing game session.

        The actual player state is created by
        GameSession.player_ready().
        """
        if not player_id:
            raise ValueError(
                "Player ID cannot be empty."
            )

        session = self.get_session(session_id)

        if session is None:
            raise ValueError(
                f"Session does not exist: {session_id}"
            )

        existing_session_id = (
            self.player_sessions.get(player_id)
        )

        if existing_session_id is not None:
            if existing_session_id == session_id:
                return session

            raise ValueError(
                f"Player is already in a session: {player_id}"
            )

        # Keep the GameServer association separate from
        # the authoritative PlayerState.
        if player_id not in session.state.players:
            if len(session.state.players) >= 2:
                raise ValueError(
                    "GAME_FULL"
                )

        self.player_sessions[player_id] = session_id

        return session

    def leave_session(
        self,
        player_id: str,
    ) -> bool:
        """
        Remove a player's session association.

        Returns True if the player was associated with a session.
        """
        if player_id not in self.player_sessions:
            return False

        del self.player_sessions[player_id]

        return True

    def get_player_session(
        self,
        player_id: str,
    ) -> GameSession | None:
        """
        Return the GameSession containing the specified player.
        """
        session_id = self.player_sessions.get(
            player_id
        )

        if session_id is None:
            return None

        return self.sessions.get(session_id)