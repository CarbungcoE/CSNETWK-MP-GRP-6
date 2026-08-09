import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Dynamically resolve path: mtgnp/server -> mtgnp -> mtgnp/data/card_catalog.json
DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "card_catalog.json"
)


@dataclass
class CardDefinition:
    """Strongly-typed representation of a card entry from card_catalog.json."""

    id: str
    name: str
    mana_cost: Dict[str, int]
    cmc: int
    type_line: str
    types: List[str]
    subtypes: List[str]
    oracle_text: str
    power: Optional[int] = None
    toughness: Optional[int] = None
    supertypes: List[str] = field(default_factory=list)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    abilities: List[Dict[str, Any]] = field(default_factory=list)


class Catalog:
    """Loads, validates, and provides lookup access to the card database."""

    def __init__(self, json_path: Optional[str] = None):
        self.json_path = Path(json_path) if json_path else DEFAULT_CATALOG_PATH
        self._cards: Dict[str, CardDefinition] = {}
        self.load()

    def load(self) -> None:
        """Reads card_catalog.json and populates the in-memory registry."""
        if not self.json_path.exists():
            raise FileNotFoundError(
                f"Catalog file missing at path: {self.json_path.resolve()}"
            )

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_cards = data.get("cards", {})
        for card_id, raw_data in raw_cards.items():
            self._cards[card_id] = CardDefinition(
                id=raw_data.get("id", card_id),
                name=raw_data.get("name", "Unknown"),
                mana_cost=raw_data.get("mana_cost", {}),
                cmc=raw_data.get("cmc", 0),
                type_line=raw_data.get("type_line", ""),
                types=raw_data.get("types", []),
                subtypes=raw_data.get("subtypes", []),
                oracle_text=raw_data.get("oracle_text", ""),
                power=raw_data.get("power"),
                toughness=raw_data.get("toughness"),
                supertypes=raw_data.get("supertypes", []),
                effects=raw_data.get("effects", []),
                abilities=raw_data.get("abilities", []),
            )

    def get(self, card_id: str) -> Optional[CardDefinition]:
        """Retrieves a single card by its ID key."""
        return self._cards.get(card_id)

    def contains(self, card_id: str) -> bool:
        """Returns True if the card ID exists in the catalog."""
        return card_id in self._cards

    def list_all_ids(self) -> List[str]:
        """Returns all registered card IDs."""
        return list(self._cards.keys())

    def filter_by_type(self, card_type: str) -> List[CardDefinition]:
        """Returns all cards matching a specific primary type (e.g., 'Instant', 'Creature')."""
        return [
            card
            for card in self._cards.values()
            if card_type.capitalize() in [t.capitalize() for t in card.types]
        ]