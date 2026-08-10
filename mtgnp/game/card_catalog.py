import csv
from pathlib import Path


class CardCatalog:
    """Loads the authoritative MTGNP fixed card set from the master CSV."""

    def __init__(self, csv_path: str | Path | None = None):
        if csv_path is None:
            csv_path = Path(__file__).resolve().parents[2] / "mtgnp_master_card_list - Master Card List.csv"
        self.csv_path = Path(csv_path)
        self.cards: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))

        if len(rows) < 3:
            raise ValueError("Master card list is empty or malformed")

        headers = [h.strip() for h in rows[1]]
        for row in rows[2:]:
            if not row or not row[0].strip():
                continue
            row = row + [""] * (len(headers) - len(row))
            data = {headers[i]: row[i].strip() for i in range(len(headers))}
            base = data["Card ID Base"]
            data["CMC"] = int(data["CMC"] or 0)
            data["W"] = int(data["W"] or 0)
            data["U"] = int(data["U"] or 0)
            data["B"] = int(data["B"] or 0)
            data["R"] = int(data["R"] or 0)
            data["G"] = int(data["G"] or 0)
            data["Generic"] = int(data["Generic"] or 0)
            if data["Power"] not in {"", "-"}:
                data["Power"] = int(data["Power"])
            if data["Toughness"] not in {"", "-"}:
                data["Toughness"] = int(data["Toughness"])
            self.cards[base] = data

    def get_by_instance_id(self, card_id: str) -> dict | None:
        if not isinstance(card_id, str) or "_" not in card_id:
            return None
        base = card_id.rsplit("_", 1)[0]
        card = self.cards.get(base)
        if card is None:
            return None
        result = dict(card)
        result["instance_id"] = card_id
        result["base_id"] = base
        return result

    def get(self, base_id: str) -> dict | None:
        card = self.cards.get(base_id)
        return dict(card) if card else None

    def is_known_instance(self, card_id: str) -> bool:
        return self.get_by_instance_id(card_id) is not None
