"""
Principled Evidence Request Simulator
Implements PRD §7.4: Deterministic, non-arbitrary simulated customer responses.
"""

from typing import Dict, Any, Optional

class EvidenceSimulator:
    @staticmethod
    def simulate_response(
        trigger_type: str,
        is_recurring_dispute: bool,
        is_travel_signature: bool,
        is_in_profile_new_device: bool,
        is_fraud_pattern_detected: bool,
        has_shared_ring_or_proxy: bool
    ) -> Dict[str, Any]:
        """Simulates customer/analyst responses based on objective evidence signals."""
        
        # Condition 1: Recurring charge match
        if is_recurring_dispute:
            return {
                "type": "customer_validation",
                "asked_after_step": 6,
                "assumed_response": "Customer states they recognize the charge after reviewing their recurring monthly subscription history."
            }

        # Condition 2: Genuine travel (new region, no parallel home activity)
        if is_travel_signature:
            return {
                "type": "customer_validation",
                "asked_after_step": 6,
                "assumed_response": "Customer confirms they were personally traveling and authorized the transactions in this billing region."
            }

        # Condition 3: In-profile purchase on new phone
        if is_in_profile_new_device:
            return {
                "type": "customer_validation",
                "asked_after_step": 6,
                "assumed_response": "Customer confirms they upgraded to a new device and completed the online purchase themselves."
            }

        # Condition 4: Fraud pattern or proxy ring detected
        if is_fraud_pattern_detected or has_shared_ring_or_proxy:
            return {
                "type": "customer_validation",
                "asked_after_step": 6,
                "assumed_response": "Customer states they did not make or authorize these purchases and still retain physical possession of their card."
            }

        # Condition 5: Trigger is a direct customer dispute
        if trigger_type == "customer_report":
            return {
                "type": "customer_validation",
                "asked_after_step": 6,
                "assumed_response": "Customer reiterates that the charge is completely unrecognized and requests immediate card protection."
            }

        # Default Condition 6: No reply within 24 hours
        return {
            "type": "customer_validation",
            "asked_after_step": 6,
            "assumed_response": "No cardholder response received within 24 hours of notification."
        }
