"""
Unit Tests for Graph Engine Tools T1 - T16
"""

import pytest
from src.data.graph_engine import GraphEngine

@pytest.fixture(scope="module")
def engine():
    return GraphEngine.get_instance(".")

def test_t1_case_context(engine):
    ctx = engine.t1_case_context("HHG-001")
    assert ctx["case_id"] == "HHG-001"
    assert ctx["flagged_txn_id"] == "3514030"
    assert ctx["card_id"] == "C12382-K1"
    assert ctx["customer_id"] == "C12382"

def test_t3_card_baseline(engine):
    b = engine.t3_card_baseline("C12382-K1")
    assert b["total_txns"] > 0
    assert b["median_amt"] > 0
    assert b["p95_amt"] >= b["median_amt"]

def test_t6_device_for_txn(engine):
    dev = engine.t6_device_for_txn(3478561)
    assert dev["has_device"] is True
    assert "SM-G935F" in dev["profile_key"]
    assert dev["is_proxy"] is True

def test_t12_ring_detector(engine):
    ring = engine.t12_ring_detector("SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080")
    assert ring["is_ring"] is True
    assert ring["is_u1_proxy_ring"] is True
    assert ring["customer_count"] >= 3

def test_t14_policy_retrieve(engine):
    pol = engine.t14_policy_retrieve("R5")
    assert "R5" in pol["rule"]
    assert "card testing" in pol["text"].lower() or "micro" in pol["text"].lower() or "testing" in pol["text"].lower()
