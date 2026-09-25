"""
Investigation Orchestrator
Executes the 10-step autonomous investigation state machine per PRD §7.2:
INTAKE -> BASELINE -> EXPAND -> DETECT -> RETRIEVE_MEMORY -> ASSESS -> REQUEST_EVIDENCE -> DECIDE -> EXPLAIN -> PERSIST
"""

import time
import os
import json
from typing import Dict, List, Any, Tuple

from src.data.graph_engine import GraphEngine
from src.engine.probability import ProbabilityModel
from src.engine.policy import PolicyEngine
from src.engine.simulator import EvidenceSimulator
from src.agent.explainer import InvestigationExplainer

class InvestigationOrchestrator:
    def __init__(self, data_dir: str = "."):
        self.engine = GraphEngine.get_instance(data_dir)

    def investigate_case(self, case_id: str) -> Dict[str, Any]:
        start_time = time.time()
        self.engine.reset_tool_counter()
        prob_model = ProbabilityModel()
        evidence_items: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # Step 1: INTAKE
        # -------------------------------------------------------------
        ctx = self.engine.t1_case_context(case_id)
        if "error" in ctx:
            raise ValueError(ctx["error"])

        flagged_tid = ctx["flagged_txn_id"]
        card_id = ctx["card_id"]
        customer_id = ctx["customer_id"]
        trigger_type = ctx["trigger_type"]
        risk_score = float(ctx["risk_score"])
        flagged_txn = ctx["flagged_txn"]

        # Look up device identity for flagged transaction
        dev_rec = self.engine.t6_device_for_txn(int(flagged_tid))

        # Initialize Prior
        current_p = prob_model.compute_prior(trigger_type, risk_score)

        evidence_items.append({
            "claim": f"Alert received via {trigger_type} on flagged transaction {flagged_tid} (${flagged_txn.get('TransactionAmt', 0.0):.2f}) with model score {risk_score:.2f}",
            "source": "external",
            "ref": f"query:case_context(case_id={case_id})",
            "entity_ids": [flagged_tid, card_id, customer_id]
        })

        # -------------------------------------------------------------
        # Step 2: BASELINE
        # -------------------------------------------------------------
        baseline = self.engine.t3_card_baseline(card_id)
        evidence_items.append({
            "claim": f"Card baseline established over {baseline['total_txns']} historical transactions: median ${baseline['median_amt']:.2f}, p95 ${baseline['p95_amt']:.2f}, modal billing region {baseline['modal_region']}",
            "source": "graph",
            "ref": f"query:card_baseline(card_id={card_id})",
            "entity_ids": [card_id]
        })

        # -------------------------------------------------------------
        # Step 3: EXPAND (Neighbors in time, device, region)
        # -------------------------------------------------------------
        window_txns = self.engine.t4_card_window(card_id, flagged_txn.get("ts", "2016-11-15 12:00:00"), hours=24)
        
        region_info = self.engine.t7_region_history(card_id, float(flagged_txn.get("addr1", 0.0) or 0.0))
        all_cards = self.engine.t8_customer_cards(customer_id)

        # -------------------------------------------------------------
        # Step 4: DETECT (Known & Undocumented Patterns)
        # -------------------------------------------------------------
        amt = float(flagged_txn.get("TransactionAmt", 0.0))
        rec_check = self.engine.t9_recurring_charge_check(card_id, amt)
        testing_check = self.engine.t10_card_testing_detector(card_id, flagged_txn.get("ts", "2016-11-15 12:00:00"))
        struct_check = self.engine.t11_structuring_detector(card_id, flagged_txn.get("ts", "2016-11-15 12:00:00"))
        
        profile_key = dev_rec.get("profile_key", "")
        ring_check = self.engine.t12_ring_detector(profile_key) if dev_rec.get("has_device") else {"is_ring": False, "is_u1_proxy_ring": False, "connected_cards": []}

        # -------------------------------------------------------------
        # Step 5: RETRIEVE MEMORY (Closed Cases)
        # -------------------------------------------------------------
        similar_cases = self.engine.t13_similar_closed_cases(pattern="card_not_present_fraud", card_id=card_id, k=3)
        similar_prior_ids = [c["case_id"] for c in similar_cases]
        policy_info = self.engine.t14_policy_retrieve("R1 R2 R6 R7 R9")

        # -------------------------------------------------------------
        # Step 6: ASSESS
        # -------------------------------------------------------------
        # Pattern identification logic
        pattern = "none"
        pattern_desc = ""
        affected_txn_ids = []
        is_recurring_dispute = (trigger_type == "customer_report") and rec_check["is_recurring"]
        has_shared_ring = ring_check["is_ring"]

        if testing_check["pattern_detected"]:
            pattern = "card_testing"
            affected_txn_ids = testing_check["affected_txn_ids"]
            current_p = prob_model.update_with_evidence(current_p, "CARD_TESTING", +0.35, "R5: Micro-authorization testing sequence confirmed")
            evidence_items.append({
                "claim": f"Card-testing ramp identified: {testing_check['micro_auth_count']} sub-$5 authorizations followed by purchase",
                "source": "graph",
                "ref": f"query:card_testing_detector(card_id={card_id})",
                "entity_ids": affected_txn_ids
            })

        elif ring_check["is_u1_proxy_ring"] or (ring_check["is_ring"] and trigger_type == "analyst_request"):
            pattern = "undocumented"
            pattern_desc = (
                f"Anonymous-proxy device ring: {ring_check['customer_count']} cardholders transacted through the identical "
                f"unusual device signature ({profile_key}) behind an anonymous proxy, indicating organized multi-account harvesting."
            )
            affected_txn_ids = [flagged_tid]
            current_p = prob_model.update_with_evidence(current_p, "DEVICE_RING", +0.35, "U1: Anonymous-proxy multi-card ring confirmed")
            evidence_items.append({
                "claim": f"Transaction linked to coordinated ring across {ring_check['customer_count']} cards sharing device {profile_key}",
                "source": "graph",
                "ref": f"query:ring_detector(device_profile_id={profile_key})",
                "entity_ids": ring_check["connected_cards"][:5] + [flagged_tid]
            })

        elif struct_check["pattern_detected"]:
            pattern = "undocumented"
            pattern_desc = (
                f"Sub-threshold structuring evasion: {struct_check['cluster_count']} online transactions executed in rapid sequence "
                f"designed to stay just below authorization thresholds (${struct_check['threshold_band']})."
            )
            affected_txn_ids = struct_check["affected_txn_ids"]
            current_p = prob_model.update_with_evidence(current_p, "STRUCTURING", +0.30, "U2: Authorization threshold evasion pattern")
            evidence_items.append({
                "claim": f"Structuring pattern: {struct_check['cluster_count']} online purchases just below authorization ceiling",
                "source": "graph",
                "ref": f"query:structuring_detector(card_id={card_id})",
                "entity_ids": affected_txn_ids
            })

        elif is_recurring_dispute:
            pattern = "none"
            current_p = prob_model.update_with_evidence(current_p, "RECURRING_MATCH", -0.40, "R7: Matched recurring monthly charge cadence")
            evidence_items.append({
                "claim": f"Flagged charge matches customer's own recurring billing pattern ({rec_check['match_count']} historical monthly occurrences)",
                "source": "graph",
                "ref": f"query:recurring_charge_check(card_id={card_id}, amount={amt})",
                "entity_ids": [flagged_tid]
            })

        elif flagged_txn.get("channel") == "in_person" and region_info["is_novel_region"]:
            if region_info["parallel_home_activity"]:
                pattern = "out_of_region_use"
                affected_txn_ids = [flagged_tid]
                current_p = prob_model.update_with_evidence(current_p, "OUT_OF_REGION_PARALLEL", +0.25, "R2: Card-present activity while home activity concurrent")
                evidence_items.append({
                    "claim": f"Out-of-region card-present use in region {flagged_txn.get('addr1')} while normal transactions simultaneously occurred at home",
                    "source": "graph",
                    "ref": f"query:region_history(card_id={card_id}, addr1={flagged_txn.get('addr1')})",
                    "entity_ids": [flagged_tid]
                })
            else:
                pattern = "none"
                current_p = prob_model.update_with_evidence(current_p, "TRAVEL_SIGNATURE", -0.20, "Travel pattern: new region without parallel home activity")
                evidence_items.append({
                    "claim": f"Cardholder activity in billing region {flagged_txn.get('addr1')} consistent with temporary travel (no concurrent home activity)",
                    "source": "graph",
                    "ref": f"query:region_history(card_id={card_id}, addr1={flagged_txn.get('addr1')})",
                    "entity_ids": [flagged_tid]
                })

        elif dev_rec.get("has_device") and dev_rec.get("is_new"):
            if dev_rec.get("is_proxy") or amt > baseline["p95_amt"]:
                pattern = "card_not_present_new_device"
                affected_txn_ids = [flagged_tid]
                current_p = prob_model.update_with_evidence(current_p, "CNP_NEW_DEVICE", +0.25, "Online transaction from anomalous new device with elevated risk")
                evidence_items.append({
                    "claim": f"Online transaction from unverified new device profile ({profile_key}) exceeding normal baseline limits",
                    "source": "graph",
                    "ref": f"query:device_for_txn(txn_id={flagged_tid})",
                    "entity_ids": [flagged_tid]
                })
            else:
                pattern = "none"
                current_p = prob_model.update_with_evidence(current_p, "NEW_DEVICE_BASELINE", -0.15, "In-profile purchase on new phone; frequent false alarm")
                evidence_items.append({
                    "claim": f"New device profile registered, but transaction amount ${amt:.2f} is well within customary card limits",
                    "source": "graph",
                    "ref": f"query:device_for_txn(txn_id={flagged_tid})",
                    "entity_ids": [flagged_tid]
                })
        else:
            if trigger_type == "customer_report":
                pattern = "card_not_present_fraud"
                affected_txn_ids = [flagged_tid]
                current_p = prob_model.update_with_evidence(current_p, "CUSTOMER_DISPUTE", +0.20, "Direct cardholder repudiation without recurring match")
            else:
                pattern = "none"
                affected_txn_ids = []

        # Tentative exposure
        exposure_usd = round(sum(float(t.get("TransactionAmt", amt)) for t in window_txns if str(t.get("TransactionID")) in affected_txn_ids), 2) if affected_txn_ids else (amt if pattern != "none" else 0.0)
        if pattern != "none" and not affected_txn_ids:
            affected_txn_ids = [flagged_tid]
            exposure_usd = round(amt, 2)

        # Provisional verdict
        provisional_verdict = "fraud" if current_p >= 0.70 else ("legitimate" if current_p <= 0.25 else "uncertain")

        # -------------------------------------------------------------
        # Step 7: REQUEST EVIDENCE (Simulated)
        # -------------------------------------------------------------
        sim_res = EvidenceSimulator.simulate_response(
            trigger_type=trigger_type,
            is_recurring_dispute=is_recurring_dispute,
            is_travel_signature=(pattern == "none" and region_info.get("prior_region_txns", 0) <= 1 and not region_info.get("parallel_home_activity")),
            is_in_profile_new_device=(pattern == "none" and dev_rec.get("is_new") and amt <= baseline["p95_amt"]),
            is_fraud_pattern_detected=(pattern in {"card_testing", "undocumented", "out_of_region_use", "card_not_present_new_device"}),
            has_shared_ring_or_proxy=has_shared_ring
        )

        evidence_requests = [sim_res]
        assumed_resp = sim_res["assumed_response"]

        # Update probability with customer response
        if "confirm" in assumed_resp.lower() or "recognize" in assumed_resp.lower():
            current_p = prob_model.update_with_evidence(current_p, "CUSTOMER_CONFIRMATION", -0.45, "R3: Cardholder confirmed purchase as legitimate")
            verdict = "legitimate"
            pattern = "none"
            affected_txn_ids = []
            exposure_usd = 0.0
            status = "closed_legitimate"
            stop_reason = "Customer confirmation settled the alert; transaction verified within cardholder baseline."
        elif "did not make" in assumed_resp.lower() or "unrecognized" in assumed_resp.lower():
            current_p = prob_model.update_with_evidence(current_p, "CUSTOMER_DENIAL", +0.25, "R2: Cardholder repudiated transaction")
            verdict = "fraud"
            status = "closed_fraud"
            stop_reason = "Customer denial settled the verdict; card compromised and protected."
        else:
            verdict = "uncertain" if current_p < 0.70 else "fraud"
            status = "escalated" if verdict == "uncertain" else "closed_fraud"
            stop_reason = "No response within 24 hours; escalated/monitored in accordance with policy."

        evidence_items.append({
            "claim": f"Cardholder response: {assumed_resp}",
            "source": "customer",
            "ref": "evidence_request:1",
            "entity_ids": [customer_id, card_id]
        })

        # -------------------------------------------------------------
        # Step 8: DECIDE (Policy Engine)
        # -------------------------------------------------------------
        initial_actions = PolicyEngine.evaluate_initial_actions(
            verdict=provisional_verdict,
            probability=current_p,
            exposure_usd=exposure_usd,
            pattern=pattern,
            is_single_signal=(trigger_type == "risk_score" and not has_shared_ring),
            is_recurring_dispute=is_recurring_dispute,
            has_shared_ring=has_shared_ring
        )

        final_actions, what_changed = PolicyEngine.evaluate_final_actions(
            verdict=verdict,
            final_probability=current_p,
            exposure_usd=exposure_usd,
            pattern=pattern,
            assumed_response=assumed_resp,
            has_shared_ring=has_shared_ring,
            connected_cards=ring_check.get("connected_cards", []),
            is_recurring_dispute=is_recurring_dispute,
            initial_actions=initial_actions
        )

        has_file_report = any(a.get("action") == "FILE_REPORT" for a in final_actions)

        # -------------------------------------------------------------
        # Step 9: EXPLAIN (Summary & SAR)
        # -------------------------------------------------------------
        summary = InvestigationExplainer.generate_case_summary(
            case_id=case_id,
            verdict=verdict,
            pattern=pattern,
            card_id=card_id,
            customer_id=customer_id,
            exposure_usd=exposure_usd,
            evidence_claims=[e["claim"] for e in evidence_items]
        )

        sar_obj = {
            "file": has_file_report,
            "reason": "Policy §3a: Exposure exceeds $1,000 or linked to shared multi-account infrastructure" if has_file_report else "",
            "narrative": "",
            "subjects": [],
            "total_amount_usd": 0.0,
            "activity_dates": []
        }

        if has_file_report:
            dates = [flagged_txn.get("ts", "2016-11-20").split()[0]]
            sar_narrative = InvestigationExplainer.generate_sar_narrative(
                case_id=case_id,
                customer_id=customer_id,
                card_id=card_id,
                affected_txns=[flagged_txn],
                connected_cards=ring_check.get("connected_cards", []),
                device_profile=profile_key,
                pattern=pattern,
                pattern_description=pattern_desc,
                exposure_usd=exposure_usd,
                dates=dates
            )
            subjects = [customer_id, card_id] + ring_check.get("connected_cards", [])[:3]
            sar_obj.update({
                "narrative": sar_narrative,
                "subjects": subjects,
                "total_amount_usd": exposure_usd,
                "activity_dates": [dates[0], dates[-1]]
            })

        # -------------------------------------------------------------
        # Step 10: PERSIST (Memory write-back)
        # -------------------------------------------------------------
        case_payload = {
            "case_id": case_id,
            "status": status,
            "verdict": verdict,
            "fraud_probability": round(current_p, 2),
            "pattern": pattern,
            "pattern_description": pattern_desc,
            "affected_txn_ids": [str(x) for x in affected_txn_ids],
            "first_suspicious_txn_id": str(affected_txn_ids[0]) if affected_txn_ids else "",
            "connected_card_ids": ring_check.get("connected_cards", [])[:10],
            "connected_device_profiles": [profile_key] if profile_key and profile_key != "none" else [],
            "exposure_usd": exposure_usd if verdict != "legitimate" else 0.0,
            "evidence": evidence_items,
            "similar_prior_cases": similar_prior_ids,
            "summary": summary,
            "written_to_graph": True,
            "graph_case_id": f"CASE-2016-{case_id.replace('HHG-', '')}"
        }

        graph_id = self.engine.t15_write_case(case_payload)
        case_payload["graph_case_id"] = graph_id

        latency_s = round(time.time() - start_time, 2)
        tool_calls = self.engine.get_tool_calls()
        estimated_tokens = 2400 + (len(evidence_items) * 180) + (850 if has_file_report else 0)

        final_record = {
            "case_id": case_id,
            "case": case_payload,
            "evidence_requests": evidence_requests,
            "next_best_actions": {
                "initial": initial_actions,
                "final": final_actions,
                "what_changed": what_changed
            },
            "sar": sar_obj,
            "stop_reason": stop_reason,
            "tool_calls": tool_calls,
            "tokens": estimated_tokens,
            "latency_s": latency_s
        }

        return final_record
