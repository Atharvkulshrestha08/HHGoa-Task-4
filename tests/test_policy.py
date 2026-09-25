"""
Unit Tests for Policy Engine & Routing Rules
"""

import pytest
from src.engine.policy import PolicyEngine, VALID_ACTIONS

def test_routing_table():
    assert PolicyEngine.get_route("DECLINE_TRANSACTION") == "L1"
    assert PolicyEngine.get_route("BLOCK_CARD", exposure_usd=500.0) == "L1"
    assert PolicyEngine.get_route("BLOCK_CARD", exposure_usd=2500.0) == "L1"
    assert PolicyEngine.get_route("BLOCK_CARD", exposure_usd=2500.01) == "L2"
    assert PolicyEngine.get_route("BLOCK_CARD", exposure_usd=5000.0) == "L2"
    assert PolicyEngine.get_route("BLOCK_ALL_CARDS") == "L2"
    assert PolicyEngine.get_route("FILE_REPORT") == "L2"
    assert PolicyEngine.get_route("ALLOW_TRANSACTION") == "auto"
    assert PolicyEngine.get_route("MONITOR_CARD") == "auto"
    assert PolicyEngine.get_route("VERIFY_WITH_CUSTOMER") == "auto"
    assert PolicyEngine.get_route("CREATE_CASE") == "auto"
    assert PolicyEngine.get_route("CLOSE_NO_FRAUD") == "auto"

def test_rule_r1_weak_signal():
    actions = PolicyEngine.evaluate_initial_actions(
        verdict="uncertain",
        probability=0.45,
        exposure_usd=100.0,
        pattern="none",
        is_single_signal=True,
        is_recurring_dispute=False,
        has_shared_ring=False
    )
    action_names = [a["action"] for a in actions]
    assert "VERIFY_WITH_CUSTOMER" in action_names
    assert "BLOCK_CARD" not in action_names

def test_rule_r2_denial_and_sar_gate():
    final_actions, what_changed = PolicyEngine.evaluate_final_actions(
        verdict="fraud",
        final_probability=0.85,
        exposure_usd=1500.0,
        pattern="card_not_present_fraud",
        assumed_response="Customer denies charge",
        has_shared_ring=False,
        connected_cards=[],
        is_recurring_dispute=False,
        initial_actions=[]
    )
    action_names = [a["action"] for a in final_actions]
    assert "BLOCK_CARD" in action_names
    assert "CREATE_CASE" in action_names
    assert "FILE_REPORT" in action_names

def test_rule_r3_confirmation_cleared():
    final_actions, what_changed = PolicyEngine.evaluate_final_actions(
        verdict="legitimate",
        final_probability=0.10,
        exposure_usd=0.0,
        pattern="none",
        assumed_response="Customer confirms transaction",
        has_shared_ring=False,
        connected_cards=[],
        is_recurring_dispute=False,
        initial_actions=[]
    )
    action_names = [a["action"] for a in final_actions]
    assert "ALLOW_TRANSACTION" in action_names
    assert "CLOSE_NO_FRAUD" in action_names
    assert "BLOCK_CARD" not in action_names
