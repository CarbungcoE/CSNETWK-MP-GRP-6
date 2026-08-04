import socket
from typing import Dict, Any, Callable, Optional


# PDU CREATION HELPERS

def create_pdu(pdu_type: str, seq_num: int, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Base factory function to build a structured MTGNP PDU.
    """
    pdu = {
        "type": pdu_type,
        "seq_num": seq_num,
    }
    if payload:
        pdu.update(payload)
    return pdu


def create_error_pdu(seq_num: int, code: int, message: str) -> Dict[str, Any]:
    """Helper to build standard ERROR PDUs."""
    return create_pdu("ERROR", seq_num, {
        "error_code": code,
        "message": message
    })


def create_ack_pdu(seq_num: int, acknowledged_seq: int) -> Dict[str, Any]:
    """Helper to build ACK PDUs."""
    return create_pdu("ACK", seq_num, {
        "ack_seq_num": acknowledged_seq
    })


# PDU VALIDATION

class PDUValidationError(Exception):
    """Custom exception raised when a received PDU is malformed."""
    pass


def validate_pdu(pdu: Any) -> None:
    """
    Validates basic structural requirements common to ALL incoming PDUs.
    Raises PDUValidationError if structure is invalid.
    """
    if not isinstance(pdu, dict):
        raise PDUValidationError("PDU payload must be a JSON object (dict).")

    if "type" not in pdu or not isinstance(pdu["type"], str):
        raise PDUValidationError("PDU missing valid string field 'type'.")

    if "seq_num" not in pdu or not isinstance(pdu["seq_num"], int):
        raise PDUValidationError("PDU missing valid integer field 'seq_num'.")


# DISPATCH ROUTER

class PDUDispatcher:
    """
    Routes validated PDUs to registered handler functions based on their 'type'.
    """

    def __init__(self):
        # Maps PDU type strings to handler functions
        # e.g., "JOIN_GAME": self.handle_join_game
        self._handlers: Dict[str, Callable[[socket.socket, Dict[str, Any]], None]] = {}

    def register(self, pdu_type: str, handler_func: Callable):
        """Registers a handler callback for a specific PDU type."""
        self._handlers[pdu_type] = handler_func

    def dispatch(self, client_sock: socket.socket, pdu: Dict[str, Any]) -> None:
        """
        Validates incoming PDU and routes it to its handler.
        """
        # 1. Validate structure
        validate_pdu(pdu)

        pdu_type = pdu["type"]

        # 2. Lookup handler
        handler = self._handlers.get(pdu_type)
        if not handler:
            raise PDUValidationError(f"Unknown or unhandled PDU type: '{pdu_type}'")

        # 3. Execute handler
        handler(client_sock, pdu)

# ^ above is for dispatch mechanism under TCP Server: connection handling, framing, dispatch
# ADD HERE: PDU serialisation/deserialisation (all 25 PDU types)