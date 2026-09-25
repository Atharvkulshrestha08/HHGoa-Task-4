"""
Deterministic Fraud Policy Engine
Implements Fraud Policy v1.0, Rules R1-R10, and approval routing (auto, L1, L2).
No LLM dependencies.
"""

from typing import Dict, List, Any, Tuple

VALID_ACTIONS = {
    "ALLOW_TRANSACTION",
    "DECLINE_TRANSACTION",
    "MONITOR_CARD",
    "MONITOR_CONNECTED_CARDS",
    "WARN_CUSTOMER",
    "VERIFY_WITH_CUSTOMER",
    "STEP_UP_AUTH",
    "BLOCK_CARD",
    "BLOCK_ALL_CARDS",
    "GENERATE_REPORT",
    "CREATE_CASE",
    "FILE_REPORT",
    "ESCALATE_TO_ANALYST",
    "CLOSE_NO_FRAUD"
}

class PolicyEngine:
    @staticmethod
    def get_route(action: str, exposure_usd: float = 0.0) -> str:
        """Enforces Policy §2 approval routing table."""
        if action == "DECLINE_TRANSACTION":
            return "L1"
        elif action == "BLOCK_CARD":
            return "L1" if exposure_usd <= 2500.0 else "L2"
        elif action in {"BLOCK_ALL_CARDS", "FILE_REPORT"}:
            return "L2"
        else:
            return "auto"

    @classmethod
    def evaluate_initial_actions(
        cls,
        verdict: str,
        probability: float,
        exposure_usd: float,
        pattern: str,
        is_single_signal: bool,
        is_recurring_dispute: bool,
        has_shared_ring: bool
    ) -> List[Dict[str, str]]:
        """Determines initial actions before evidence request response."""
        actions: List[Dict[str, str]] = []

        if verdict == "legitimate":
            actions.append({"action": "ALLOW_TRANSACTION", "route": "auto", "reason": "R3: Legitimate activity confirmed"})
            actions.append({"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R3: Normal profile consistency"})
            return actions

        # R7: Disputed recurring charge
        if is_recurring_dispute:
            actions.append({"action": "CREATE_CASE", "route": "auto", "reason": "R7: Recurring charge dispute record opened"})
            actions.append({"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R7: Remind customer of historical recurring cadence"})
            actions.append({"action": "WARN_CUSTOMER", "route": "auto", "reason": "R7: Inform cardholder of merchant billing cycle"})
            return actions

        # R5: Card testing initial
        if pattern == "card_testing":
            actions.append({"action": "DECLINE_TRANSACTION", "route": "L1", "reason": "R5: Testing sequence observed, decline pending auth"})
            actions.append({"action": "STEP_UP_AUTH", "route": "auto", "reason": "R5: Challenge cardholder identity before blocking"})
            return actions

        # R1: Verify before block on weak signal
        if is_single_signal and probability < 0.70:
            actions.append({"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: Single signal with probability below 0.70; verify before blocking"})
            if exposure_usd >= 300.0:
                actions.append({"action": "MONITOR_CARD", "route": "auto", "reason": "R1: Heightened card monitoring pending verification"})
            return actions

        # Default provisional action
        if probability >= 0.70:
            route = cls.get_route("BLOCK_CARD", exposure_usd)
            actions.append({"action": "BLOCK_CARD", "route": route, "reason": f"R2: Assessed probability {probability:.2f} warrants card block"})
            actions.append({"action": "CREATE_CASE", "route": "auto", "reason": "Policy §3a: Open case for confirmed fraud suspicion"})
            if exposure_usd > 1000.0 or has_shared_ring:
                actions.append({"action": "FILE_REPORT", "route": "L2", "reason": "Policy §3a: Exposure exceeds $1,000 or linked to shared ring"})
        else:
            actions.append({"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: Ambiguous activity requires customer clarification"})

        return actions

    @classmethod
    def evaluate_final_actions(
        cls,
        verdict: str,
        final_probability: float,
        exposure_usd: float,
        pattern: str,
        assumed_response: str,
        has_shared_ring: bool,
        connected_cards: List[str],
        is_recurring_dispute: bool,
        initial_actions: List[Dict[str, str]]
    ) -> Tuple[List[Dict[str, str]], str]:
        """Determines final actions after evidence response and generates what_changed."""
        final_actions: List[Dict[str, str]] = []

        if verdict == "legitimate" or "confirms" in assumed_response.lower() or "recognizes" in assumed_response.lower():
            final_actions.append({"action": "ALLOW_TRANSACTION", "route": "auto", "reason": "R3: Customer confirmed transaction as legitimate"})
            final_actions.append({"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R3: Alert cleared after cardholder confirmation"})
            what_changed = "Customer confirmation cleared the alert; previous provisional holds replaced with CLOSE_NO_FRAUD."
            return final_actions, what_changed

        if is_recurring_dispute:
            final_actions.append({"action": "CREATE_CASE", "route": "auto", "reason": "R7: Record customer dispute in graph"})
            final_actions.append({"action": "WARN_CUSTOMER", "route": "auto", "reason": "R7: Customer notified of recurring subscription pattern"})
            final_actions.append({"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R7: Dispute resolved as legitimate recurring charge"})
            what_changed = "Merchant recurring billing confirmed; avoided card block per Rule R7."
            return final_actions, what_changed

        # Fraud confirmed / Customer denied
        if verdict == "fraud" or "denies" in assumed_response.lower() or final_probability >= 0.70:
            route = cls.get_route("BLOCK_CARD", exposure_usd)
            final_actions.append({"action": "BLOCK_CARD", "route": route, "reason": f"R2: Unauthorized activity confirmed; exposure ${exposure_usd:,.2f}"})
            final_actions.append({"action": "CREATE_CASE", "route": "auto", "reason": "R2: Case logged to graph with evidence"})

            # SAR Filing Gate (§3a)
            needs_sar = (exposure_usd > 1000.0) or has_shared_ring or (pattern == "undocumented")
            if needs_sar:
                reason = "R2/R6: Shared ring infrastructure detected" if has_shared_ring else (
                    "R9: Undocumented coordinated pattern" if pattern == "undocumented" else "Policy §3a: Exposure exceeds $1,000 threshold"
                )
                final_actions.append({"action": "FILE_REPORT", "route": "L2", "reason": reason})

            if has_shared_ring and connected_cards:
                final_actions.append({
                    "action": "MONITOR_CONNECTED_CARDS",
                    "route": "auto",
                    "reason": f"R6: Linked to {len(connected_cards)} other cards on shared device"
                })

            if pattern == "undocumented":
                final_actions.append({"action": "ESCALATE_TO_ANALYST", "route": "auto", "reason": "R9: Undocumented pattern escalated for supervisory review"})

            what_changed = f"Customer denial / high evidence conviction raised probability to {final_probability:.2f}, confirming block and routing SAR based on exposure/ring linkage."
            return final_actions, what_changed

        # Uncertain cases
        if verdict == "uncertain":
            final_actions.append({"action": "MONITOR_CARD", "route": "auto", "reason": "R4/R8: Placed on 72-hour monitoring pending resolution"})
            if exposure_usd > 500.0:
                final_actions.append({"action": "ESCALATE_TO_ANALYST", "route": "auto", "reason": "R8: Uncertain verdict with exposure > $500 requires human analyst"})
            what_changed = "Evidence remained ambiguous; escalated or monitored per Rule R8 without premature block."
            return final_actions, what_changed

        return initial_actions, "nothing"
