from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class StackObject:
    """Represents a spell, activated ability, or triggered ability on the stack."""
    id: str
    controller_id: str
    source_name: str
    object_type: str  # "spell", "activated_ability", "triggered_ability"
    targets: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)


class Stack:
    """
    Manages the MTG stack zone, priority tracking across players,
    and LIFO object resolution.
    """
    def __init__(self, players: List[str]):
        self.items: List[StackObject] = []
        self.players: List[str] = players
        self.passed_priority: set = set()

    def push(self, stack_object: StackObject) -> None:
        """Pushes a new object onto the stack and resets priority passes."""
        self.items.append(stack_object)
        self.reset_priority_passes()

    def pop(self) -> Optional[StackObject]:
        """Removes and returns the top object from the stack."""
        if self.is_empty():
            return None
        return self.items.pop()

    def peek(self) -> Optional[StackObject]:
        """Returns the top object on the stack without removing it."""
        if self.is_empty():
            return None
        return self.items[-1]

    def is_empty(self) -> bool:
        """Returns True if the stack has no items remaining."""
        return len(self.items) == 0

    def pass_priority(self, player_id: str) -> bool:
        """
        Registers a priority pass for a player.
        Returns True if all active players have passed priority in succession.
        """
        if player_id in self.players:
            self.passed_priority.add(player_id)
        
        return len(self.passed_priority) >= len(self.players)

    def reset_priority_passes(self) -> None:
        """Clears accumulated priority passes whenever an action is taken or a stack item resolves."""
        self.passed_priority.clear()

    def resolve_top(self) -> Optional[StackObject]:
        """
        Pops the top item off the stack for resolution and resets priority passes.
        """
        if self.is_empty():
            return None
        
        obj = self.pop()
        self.reset_priority_passes()
        return obj

    def remove_by_id(self, object_id: str) -> Optional[StackObject]:
        """Removes a specific stack object by ID (e.g., counterspells or fizzling)."""
        for index, item in enumerate(self.items):
            if item.id == object_id:
                return self.items.pop(index)
        return None

    def serialize(self) -> List[Dict[str, Any]]:
        """Serializes the current stack state for network payload transmission."""
        return [
            {
                "id": obj.id,
                "controller_id": obj.controller_id,
                "source_name": obj.source_name,
                "object_type": obj.object_type,
                "targets": obj.targets,
                "payload": obj.payload,
            }
            for obj in reversed(self.items)  # Serializes top-of-stack first
        ]