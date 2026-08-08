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


def build_error(seq_num: int, code: str, message: str, rejected_action: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Builds an ERROR PDU (S->C)."""
    payload = {
        "code": code,
        "message": message
    }
    if rejected_action is not None:
        payload["rejected_action"] = rejected_action
    return create_pdu("ERROR", seq_num, payload)


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

# ALL 25 MTGNP PDU BUILDERS

# Game Lifecycle & Setup PDUs
def build_player_ready(seq_num: int, player_id: str, deck_list: list) -> Dict[str, Any]:
    """Builds a PLAYER_READY PDU (C->S)."""
    return create_pdu("PLAYER_READY", seq_num, {"player_id": player_id, "deck_list": deck_list})

def build_game_state_update(seq_num: int, state: dict) -> Dict[str, Any]:
    """Builds a GAME_STATE_UPDATE PDU (S->C)."""
    return create_pdu("GAME_STATE_UPDATE", seq_num, {"state": state})

def build_mulligan_choice(seq_num: int, keep: bool, cards_to_bottom: list) -> Dict[str, Any]:
    """Builds a MULLIGAN_CHOICE PDU (C->S)."""
    return create_pdu("MULLIGAN_CHOICE", seq_num, {"keep": keep, "cards_to_bottom": cards_to_bottom})

def build_phase_transition(seq_num: int, from_phase: str, to_phase: str, active_player: str, turn: int) -> Dict[str, Any]:
    """Builds a PHASE_TRANSITION PDU (S->ALL)."""
    return create_pdu("PHASE_TRANSITION", seq_num, {
        "from_phase": from_phase,
        "to_phase": to_phase,
        "active_player": active_player,
        "turn": turn
    })

def build_game_over(seq_num: int, winner_id: str, loser_id: str, reason: str) -> Dict[str, Any]:
    """Builds a GAME_OVER PDU (S->ALL)."""
    return create_pdu("GAME_OVER", seq_num, {"winner_id": winner_id, "loser_id": loser_id, "reason": reason})

def build_concede(seq_num: int, player_id: str) -> Dict[str, Any]:
    """Builds a CONCEDE PDU (C->S)."""
    return create_pdu("CONCEDE", seq_num, {"player_id": player_id})


# Priority & Actions PDUs
def build_priority_grant(seq_num: int, player_id: str, time_limit_ms: int) -> Dict[str, Any]:
    """Builds a PRIORITY_GRANT PDU (S->C)."""
    return create_pdu("PRIORITY_GRANT", seq_num, {"player_id": player_id, "time_limit_ms": time_limit_ms})

def build_priority_pass(seq_num: int) -> Dict[str, Any]:
    """Builds a PRIORITY_PASS PDU (C->S)."""
    return create_pdu("PRIORITY_PASS", seq_num)

def build_cast_spell(seq_num: int, card_id: str, targets: list, mana_payment: dict) -> Dict[str, Any]:
    """Builds a CAST_SPELL PDU (C->S)."""
    return create_pdu("CAST_SPELL", seq_num, {"card_id": card_id, "targets": targets, "mana_payment": mana_payment})

def build_activate_ability(seq_num: int, source_id: str, ability_index: int, targets: list, cost_payment: dict) -> Dict[str, Any]:
    """Builds an ACTIVATE_ABILITY PDU (C->S)."""
    return create_pdu("ACTIVATE_ABILITY", seq_num, {
        "source_id": source_id,
        "ability_index": ability_index,
        "targets": targets,
        "cost_payment": cost_payment
    })

def build_play_land(seq_num: int, card_id: str) -> Dict[str, Any]:
    """Builds a PLAY_LAND PDU (C->S)."""
    return create_pdu("PLAY_LAND", seq_num, {"card_id": card_id})

def build_discard(seq_num: int, card_ids: list) -> Dict[str, Any]:
    """Builds a DISCARD PDU (C->S)."""
    return create_pdu("DISCARD", seq_num, {"card_ids": card_ids})


# Stack & Trigger PDUs
def build_stack_push(seq_num: int, stack_item_id: str, item_type: str, source: str, targets: list, controller: str) -> Dict[str, Any]:
    """Builds a STACK_PUSH PDU (S->ALL)."""
    return create_pdu("STACK_PUSH", seq_num, {
        "stack_item_id": stack_item_id,
        "item_type": item_type,
        "source": source,
        "targets": targets,
        "controller": controller
    })

def build_stack_resolve(seq_num: int, stack_item_id: str, result: str, state_changes: list) -> Dict[str, Any]:
    """Builds a STACK_RESOLVE PDU (S->ALL)."""
    return create_pdu("STACK_RESOLVE", seq_num, {
        "stack_item_id": stack_item_id,
        "result": result,
        "state_changes": state_changes
    })

def build_trigger_order(seq_num: int, player_id: str, trigger_ids: list) -> Dict[str, Any]:
    """Builds a TRIGGER_ORDER PDU (S->C)."""
    return create_pdu("TRIGGER_ORDER", seq_num, {"player_id": player_id, "trigger_ids": trigger_ids})

def build_trigger_order_response(seq_num: int, ordered_trigger_ids: list) -> Dict[str, Any]:
    """Builds a TRIGGER_ORDER_RESPONSE PDU (C->S)."""
    return create_pdu("TRIGGER_ORDER_RESPONSE", seq_num, {"ordered_trigger_ids": ordered_trigger_ids})

def build_trigger_choice(seq_num: int, trigger_id: str, source_id: str, effect_summary: str, requires_target: bool, legal_targets: list) -> Dict[str, Any]:
    """Builds a TRIGGER_CHOICE PDU (S->C)."""
    return create_pdu("TRIGGER_CHOICE", seq_num, {
        "trigger_id": trigger_id,
        "source_id": source_id,
        "effect_summary": effect_summary,
        "requires_target": requires_target,
        "legal_targets": legal_targets
    })

def build_trigger_choice_response(seq_num: int, trigger_id: str, accept: bool, chosen_target: Optional[str] = None) -> Dict[str, Any]:
    """Builds a TRIGGER_CHOICE_RESPONSE PDU (C->S)."""
    payload = {"trigger_id": trigger_id, "accept": accept}
    if chosen_target is not None:
        payload["chosen_target"] = chosen_target
    return create_pdu("TRIGGER_CHOICE_RESPONSE", seq_num, payload)


# Combat PDUs
def build_declare_attackers(seq_num: int, attackers: list) -> Dict[str, Any]:
    """Builds a DECLARE_ATTACKERS PDU (C->S)."""
    return create_pdu("DECLARE_ATTACKERS", seq_num, {"attackers": attackers})

def build_declare_blockers(seq_num: int, blockers: list) -> Dict[str, Any]:
    """Builds a DECLARE_BLOCKERS PDU (C->S)."""
    return create_pdu("DECLARE_BLOCKERS", seq_num, {"blockers": blockers})

def build_assign_damage_order(seq_num: int, attacker_id: str, blocker_order: list) -> Dict[str, Any]:
    """Builds an ASSIGN_DAMAGE_ORDER PDU (C->S)."""
    return create_pdu("ASSIGN_DAMAGE_ORDER", seq_num, {"attacker_id": attacker_id, "blocker_order": blocker_order})

def build_combat_damage_result(seq_num: int, damage_events: list, life_totals: dict, creatures_died: list) -> Dict[str, Any]:
    """Builds a COMBAT_DAMAGE_RESULT PDU (S->ALL)."""
    return create_pdu("COMBAT_DAMAGE_RESULT", seq_num, {
        "damage_events": damage_events,
        "life_totals": life_totals,
        "creatures_died": creatures_died
    })


# Network / Heartbeat PDUs
def build_ping(seq_num: int, timestamp: int) -> Dict[str, Any]:
    """Builds a PING PDU (C->S)."""
    return create_pdu("PING", seq_num, {"timestamp": timestamp})

def build_pong(seq_num: int, timestamp: int) -> Dict[str, Any]:
    """Builds a PONG PDU (S->C)."""
    return create_pdu("PONG", seq_num, {"timestamp": timestamp})