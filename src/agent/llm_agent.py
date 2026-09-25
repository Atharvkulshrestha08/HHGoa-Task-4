"""
Real-Time AI Fraud Investigation Agent powered by Google Gemini (gemini-3.6-flash).
ReAct Loop: Thought -> Tool Call -> Observation -> Reasoning -> Action
"""

import os
import json
import time
from typing import Dict, List, Any, Optional, Callable
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

SYSTEM_PROMPT = """You are a senior fraud investigation AI agent at a major card issuer. You have access to a knowledge graph containing 590,742 transactions, 144,432 device identity records, and 5,565 resolved historical cases.

YOUR ROLE:
- You investigate fraud alerts by querying the graph, analyzing evidence, and recommending actions.
- You are an INTERACTIVE agent. The analyst talks to you, you reason out loud, you call tools to gather evidence, and you explain your findings step by step.
- You are NOT a static report generator. You THINK through each case dynamically.

INVESTIGATION STEPS:
1. When given a case (e.g. "Investigate HHG-001"), call case_context first to get the alert details and flagged transaction.
2. Systematically gather baseline and anomaly evidence: card_baseline, card_window, device_for_txn, region_history.
3. Run specialized pattern detectors: card_testing_detector, structuring_detector, ring_detector.
4. Search case memory: similar_closed_cases to find how past analysts handled similar situations.
5. Synthesize your findings into a verdict, fraud probability, and recommended actions.

CALIBRATION & POLICY:
- High risk score on a new device or new region alone is often a FALSE ALARM if amounts and channels match baseline.
- Card testing: 3+ micro-auths (<$5) followed by a larger purchase -> DECLINE + STEP_UP (R5).
- Shared device / ring: Multiple cards using rare device/proxy -> CREATE_CASE + FILE_REPORT + MONITOR (R6/U1).
- Recurring charge dispute: Same merchant/amount/interval -> CLOSE_NO_FRAUD or WARN (R7). Never block.
- Structuring: Rapid online txns just below $500 or $1000 thresholds (U2).
- Approval routes: auto (ALLOW, MONITOR, VERIFY, STEP_UP, CREATE_CASE), L1 (DECLINE, BLOCK <= $2500), L2 (BLOCK > $2500, BLOCK_ALL, FILE_REPORT).

When presenting final conclusions:
- State VERDICT (fraud / legitimate / uncertain)
- State FRAUD PROBABILITY (0.0 to 1.0)
- State PATTERN NAME
- List AFFECTED TRANSACTIONS & TOTAL EXPOSURE
- List RECOMMENDED ACTIONS with approval routing and rule citation
- If SAR required, provide SAR narrative structure."""


class FraudInvestigationAgent:
    """Interactive AI Agent with Gemini automatic tool-calling ReAct loop."""

    def __init__(self, data_dir: str = "."):
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY / GOOGLE_API_KEY not found in .env")

        genai.configure(api_key=self.api_key)
        self.model_name = "models/gemini-flash-latest"

        # Load graph engine
        from src.data.graph_engine import GraphEngine
        self.engine = GraphEngine.get_instance(data_dir)
        self.data_dir = self.engine.data_dir

        self.tool_call_log: List[Dict[str, Any]] = []
        self.total_tokens: int = 0
        self.chat_session = None
        self._init_chat()

    def _get_tools(self) -> List[Callable]:
        """Expose Python tool functions to Gemini."""
        engine = self.engine

        def case_context(case_id: str) -> str:
            """Fetch alert details, flagged transaction, card, customer, trigger, and risk score for a case."""
            res = engine.t1_case_context(case_id)
            return json.dumps(res, default=str)

        def card_history(card_id: str, limit: int = 30) -> str:
            """Fetch recent transaction history for a card/customer ordered by timestamp."""
            res = engine.t2_card_history(card_id, limit)
            return json.dumps(res[:25], default=str)

        def card_baseline(card_id: str) -> str:
            """Get statistical baseline for a card: median, p95 amount, modal region, channel distribution."""
            res = engine.t3_card_baseline(card_id)
            return json.dumps(res, default=str)

        def card_window(card_id: str, anchor_ts: str, hours: int = 24) -> str:
            """Get transactions for a card within hours around an anchor timestamp."""
            res = engine.t4_card_window(card_id, anchor_ts, hours)
            return json.dumps(res[:25], default=str)

        def device_neighbors(device_profile_key: str) -> str:
            """Find cards and customers sharing a device profile, with rarity score."""
            res = engine.t5_device_neighbors(device_profile_key)
            return json.dumps(res, default=str)

        def device_for_txn(txn_id: int) -> str:
            """Get device and identity record for a transaction: OS, browser, proxy status, new device flag."""
            res = engine.t6_device_for_txn(txn_id)
            return json.dumps(res, default=str)

        def region_history(card_id: str, addr1: float) -> str:
            """Check if a card transacted in this billing region before and whether parallel home activity exists."""
            res = engine.t7_region_history(card_id, addr1)
            return json.dumps(res, default=str)

        def customer_cards(customer_id: str) -> str:
            """Get all cards owned by customer for R10 multi-card block evaluation."""
            res = engine.t8_customer_cards(customer_id)
            return json.dumps(res, default=str)

        def recurring_charge_check(card_id: str, amount: float, tol: float = 1.0) -> str:
            """Check if amount matches a monthly recurring charge cadence (Rule R7)."""
            res = engine.t9_recurring_charge_check(card_id, amount, tol)
            return json.dumps(res, default=str)

        def card_testing_detector(card_id: str, anchor_ts: str) -> str:
            """Detect card testing: 3+ micro authorizations under $5 followed by larger purchase."""
            res = engine.t10_card_testing_detector(card_id, anchor_ts)
            return json.dumps(res, default=str)

        def structuring_detector(card_id: str, anchor_ts: str) -> str:
            """Detect structuring: rapid transactions just under $500 or $1000 thresholds (Pattern U2)."""
            res = engine.t11_structuring_detector(card_id, anchor_ts)
            return json.dumps(res, default=str)

        def ring_detector(device_profile_key: str, min_cards: int = 3) -> str:
            """Detect multi-card fraud ring on rare device or anonymous proxy (Pattern U1)."""
            res = engine.t12_ring_detector(device_profile_key, min_cards)
            return json.dumps(res, default=str)

        def similar_closed_cases(pattern: str, k: int = 5) -> str:
            """Search 5,565 closed historical cases for similar patterns and past analyst outcomes."""
            res = engine.t13_similar_closed_cases(pattern, k=k)
            return json.dumps(res, default=str)

        def policy_retrieve(rule_query: str) -> str:
            """Retrieve policy rule text (R1 to R10)."""
            res = engine.t14_policy_retrieve(rule_query)
            return json.dumps(res, default=str)

        return [
            case_context,
            card_history,
            card_baseline,
            card_window,
            device_neighbors,
            device_for_txn,
            region_history,
            customer_cards,
            recurring_charge_check,
            card_testing_detector,
            structuring_detector,
            ring_detector,
            similar_closed_cases,
            policy_retrieve
        ]

    def _init_chat(self):
        tools = self._get_tools()
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=SYSTEM_PROMPT,
            tools=tools
        )
        self.chat_session = self.model.start_chat(enable_automatic_function_calling=True)

    def chat(self, user_message: str, on_step: Optional[Callable] = None) -> str:
        """Execute chat turn with tool-calling ReAct loop."""
        self.engine.reset_tool_counter()

        if on_step:
            on_step("thinking", "Agent is analyzing graph context and selecting tools...")

        try:
            response = self.chat_session.send_message(user_message)

            # Inspect chat history to capture tool calls made
            if self.chat_session.history:
                for msg in self.chat_session.history[-6:]:
                    for part in msg.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            call_name = part.function_call.name
                            call_args = dict(part.function_call.args)
                            self.tool_call_log.append({
                                "tool": call_name,
                                "arguments": call_args,
                                "timestamp": time.strftime("%H:%M:%S")
                            })
                            if on_step:
                                on_step("tool_call", {"tool": call_name, "args": call_args, "iteration": 1})
                        elif hasattr(part, "function_response") and part.function_response:
                            fn_name = part.function_response.name
                            fn_out = str(part.function_response.response)[:400]
                            if on_step:
                                on_step("tool_result", {"tool": fn_name, "result": fn_out})

            final_text = response.text or ""
            if on_step:
                on_step("response", final_text)
            return final_text

        except Exception as e:
            import traceback
            traceback.print_exc()
            err_msg = f"Gemini Agent error: {e}"
            if on_step:
                on_step("error", err_msg)
            return err_msg

    def reset_conversation(self):
        """Clear conversation history."""
        self.tool_call_log = []
        self._init_chat()
