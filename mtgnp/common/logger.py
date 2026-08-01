import json

class VerboseLogger:
    def __init__(self, enabled: bool = False, label: str = "LOG"):
        self.enabled = enabled
        self.label = label

    def log_pdu(self, direction: str, pdu: dict):
        """Prints formatted PDU details to console if Verbose Mode is enabled."""
        if not self.enabled:
            return
        print(f"\n--- [{self.label}] {direction} ---")
        print(json.dumps(pdu, indent=2))
        print("-" * (len(self.label) + 12))