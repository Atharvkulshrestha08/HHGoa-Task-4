"""
Calibrated Bayesian / Log-Odds Probability Model
Implements PRD §7.3: Trigger Priors, Evidence Weights, and Probability Ladder tracking.
"""

from typing import Dict, List, Any, Tuple
import math

class ProbabilityModel:
    def __init__(self):
        self.evidence_log: List[Dict[str, Any]] = []

    def compute_prior(self, trigger_type: str, risk_score: float) -> float:
        """Determines calibrated prior based on trigger type and risk score."""
        if trigger_type == "customer_report":
            prior = 0.60
            reason = "Trigger: customer_report (denial prior 0.60)"
        elif trigger_type == "analyst_request":
            prior = 0.55
            reason = "Trigger: analyst_request (human lead prior 0.55)"
        elif risk_score >= 0.85:
            # Per PRD §3.3: high scores on new device/region are frequent false alarms
            prior = 0.30
            reason = f"Trigger: risk_score {risk_score:.2f} (counter-intuitive false-alarm baseline 0.30)"
        elif risk_score >= 0.70:
            prior = 0.30
            reason = f"Trigger: risk_score {risk_score:.2f} (moderate-high score baseline 0.30)"
        else:
            prior = 0.35
            reason = f"Trigger: risk_score {risk_score:.2f} (weak score baseline 0.35)"

        self.evidence_log.append({
            "step": "PRIOR",
            "delta": 0.0,
            "resulting_p": prior,
            "reason": reason
        })
        return prior

    @staticmethod
    def _prob_to_log_odds(p: float) -> float:
        p = max(0.001, min(0.999, p))
        return math.log(p / (1.0 - p))

    @staticmethod
    def _log_odds_to_prob(lo: float) -> float:
        return 1.0 / (1.0 + math.exp(-lo))

    def update_with_evidence(self, current_p: float, evidence_name: str, delta: float, reason: str) -> float:
        """Applies log-odds evidence delta and records ladder progression."""
        current_lo = self._prob_to_log_odds(current_p)
        new_lo = current_lo + delta
        new_p = self._log_odds_to_prob(new_lo)
        
        # Clamp to [0.02, 0.97]
        clamped_p = round(max(0.02, min(0.97, new_p)), 2)

        self.evidence_log.append({
            "step": evidence_name,
            "delta": delta,
            "resulting_p": clamped_p,
            "reason": reason
        })
        return clamped_p

    def get_ladder(self) -> List[Dict[str, Any]]:
        return list(self.evidence_log)
