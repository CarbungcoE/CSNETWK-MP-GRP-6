"""Focused MTGNP 1.0 RFC regression tests."""
from mtgnp.game.player import PlayerState
from mtgnp.server.game_session import GameSession
from mtgnp.server.dispatcher import Dispatcher
from mtgnp.server.game_server import GameServer


def players(session):
    session.state.players = {
        "player_1": PlayerState("player_1"),
        "player_2": PlayerState("player_2"),
    }


def test_first_strike_opens_priority_before_regular_damage():
    s = GameSession(); players(s)
    s.state.active_player = "player_1"
    s.state.phase = "ASSIGN_DAMAGE_ORDER"
    s.state.phase_decision_complete = True
    s.state.priority_player = "player_1"
    s.combat.atks = [{"creature_id": "a", "target": "player_2"}]
    s.state.players["player_1"].battlefield = [{"id":"a","power":2,"toughness":2,"damage":0,"tapped":True,"attacking":True,"first_strike":True}]
    s.pass_priority(); result = s.pass_priority()
    assert result["phase"] == "FIRST_STRIKE_DAMAGE"
    assert result["priority_player"] == "player_1"
    assert s.state.players["player_2"].life == 18


def test_simultaneous_life_zero_active_player_loses():
    s = GameSession(); players(s); s.state.active_player = "player_1"
    s.state.players["player_1"].life = 0; s.state.players["player_2"].life = 0
    s._check_state_based_actions()
    assert s.state.game_over
    assert s.state.winner == "player_2"


def test_visible_state_contains_exile_and_rfc_stack_shape():
    s = GameSession(); players(s)
    s.state.players["player_1"].exile = [{"id":"x"}]
    s.state.stack = [{"stack_item_id":"stk_1","item_type":"SPELL","source_id":"x","controller_id":"player_1","targets":["player_2"]}]
    state = s.get_visible_state("player_1")
    assert state["exile"]["player_1"] == [{"id":"x"}]
    assert state["stack"][0] == {"stack_item_id":"stk_1","item_type":"SPELL","source":"x","targets":["player_2"],"controller":"player_1"}


def test_trigger_controller_is_permanent_controller():
    s = GameSession(); players(s); s.state.active_player = "player_1"
    permanent = {"id":"gray_merchant_001"}
    s.state.players["player_2"].battlefield.append(permanent)
    s._fire_triggers("ETB", permanent["id"], permanent, controller_id="player_2")
    pending = s.state.pending_trigger_orders["player_2"]
    item = pending["items"][pending["trigger_ids"][0]]
    assert item["controller_id"] == "player_2"


def test_trigger_order_rejects_duplicates():
    server = GameServer(); session = server.get_or_create_session("rfc")
    server.join_session("rfc", "player_1"); server.join_session("rfc", "player_2")
    players(session)
    session.state.pending_trigger_orders["player_1"] = {
        "trigger_ids": ["a", "b"],
        "items": {
            "a": {"stack_item_id":"a","item_type":"TRIGGER_ABILITY","source_id":"a","controller_id":"player_1"},
            "b": {"stack_item_id":"b","item_type":"TRIGGER_ABILITY","source_id":"b","controller_id":"player_1"},
        },
    }
    session.state.pending_trigger_order_seq["player_1"] = 5
    result = Dispatcher(server).dispatch("player_1", {"type":"TRIGGER_ORDER_RESPONSE","seq_num":5,"ordered_trigger_ids":["a","a"]})
    assert result["code"] == "TRIGGER_ORDER_INVALID"


def test_summoning_sick_tap_ability_is_rejected_without_mutation():
    s = GameSession(); players(s); s.state.priority_player = "player_1"
    # Use a catalog permanent known to have an activated ability.
    source = {"id":"llanowar_elves_001","tapped":False,"summoning_sickness":True,"haste":False}
    s.state.players["player_1"].battlefield.append(source)
    card = s.cards.get_by_instance_id(source["id"])
    if not card:
        return
    try:
        s.activate_ability("player_1", source["id"], 0, [], {"tap":True,"mana":{}})
    except ValueError as exc:
        assert str(exc) == "ILLEGAL_ACTION"
    else:
        raise AssertionError("summoning-sick tap ability was accepted")
    assert not source["tapped"]
