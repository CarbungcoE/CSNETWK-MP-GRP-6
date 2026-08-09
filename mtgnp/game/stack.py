from typing import Any

from mtgnp.game.game_state import GameState


class StackManager:
    """
    Manages the game stack.

    StackManager does not own game state. It operates on the
    authoritative stack contained in GameState.
    """

    def __init__(self, state: GameState):
        self.state = state

    def push(self, item: dict[str, Any]) -> None:
        """
        Put an object on top of the stack.
        """
        if self.state.game_over:
            raise ValueError(
                "Cannot add an object to the stack after game over"
            )

        controller_id = item.get("controller_id")

        if controller_id is not None:
            if controller_id not in self.state.players:
                raise ValueError(
                    f"Unknown player: {controller_id}"
                )

        self.state.stack.append(item)

    def pop(self) -> dict[str, Any] | None:
        """
        Remove and return the top object from the stack.

        Returns None if the stack is empty.
        """
        if not self.state.stack:
            return None

        return self.state.stack.pop()

    def peek(self) -> dict[str, Any] | None:
        """
        Return the top object without removing it.

        Returns None if the stack is empty.
        """
        if not self.state.stack:
            return None

        return self.state.stack[-1]

    def is_empty(self) -> bool:
        """
        Return True if the stack contains no objects.
        """
        return not self.state.stack

    def size(self) -> int:
        """
        Return the number of objects currently on the stack.
        """
        return len(self.state.stack)

    def resolve_top(self) -> dict[str, Any] | None:
        """
        Remove and return the top object for resolution.
        """
        return self.pop()

    def clear(self) -> None:
        """
        Empty the stack.

        This should only be used by game-level rules that explicitly
        require the stack to be cleared.
        """
        self.state.stack.clear()