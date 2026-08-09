import csv
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Dynamically resolve paths: mtgnp/server -> mtgnp -> mtgnp/data/
DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "card_catalog.json"
)
DEFAULT_CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent / "mtgnp_master_card_list - Master Card List.csv"
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

    def __init__(
        self,
        json_path: Optional[str] = None,
        csv_path: Optional[str] = None,
    ):
        self.json_path = Path(json_path) if json_path else DEFAULT_CATALOG_PATH
        self.csv_path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH
        self._cards: Dict[str, CardDefinition] = {}
        self.load()

    def load(self) -> None:
        """Reads card_catalog.json and populates the in-memory registry.
        
        If card_catalog.json is missing or empty, builds it automatically from the master CSV.
        """
        if not self.json_path.exists() or self.json_path.stat().st_size == 0:
            self._build_catalog_from_csv()

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

    def _build_catalog_from_csv(self) -> None:
        """Parses master card list CSV and populates card_catalog.json."""
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"Cannot build catalog: Master CSV missing at path: {self.csv_path.resolve()}"
            )

        cards_dict = {}
        with open(self.csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                card_id = row.get("id", "").strip()
                if not card_id:
                    continue

                # Safely parse JSON fields or string lists
                mana_cost = {}
                raw_mana = row.get("mana_cost", "").strip()
                if raw_mana:
                    try:
                        mana_cost = json.loads(raw_mana)
                    except json.JSONDecodeError:
                        pass

                types = [
                    t.strip()
                    for t in row.get("types", "").split(",")
                    if t.strip()
                ]
                subtypes = [
                    s.strip()
                    for s in row.get("subtypes", "").split(",")
                    if s.strip()
                ]
                supertypes = [
                    sp.strip()
                    for sp in row.get("supertypes", "").split(",")
                    if sp.strip()
                ]

                cards_dict[card_id] = {
                    "id": card_id,
                    "name": row.get("name", ""),
                    "mana_cost": mana_cost,
                    "cmc": int(row["cmc"]) if row.get("cmc", "").isdigit() else 0,
                    "type_line": row.get("type_line", ""),
                    "types": types,
                    "subtypes": subtypes,
                    "supertypes": supertypes,
                    "oracle_text": row.get("oracle_text", ""),
                    "power": int(row["power"]) if row.get("power", "").isdigit() else None,
                    "toughness": int(row["toughness"]) if row.get("toughness", "").isdigit() else None,
                }

        # Ensure parent directory exists and dump JSON
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump({"cards": cards_dict}, f, indent=2)

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