"""
Strict Answer Format Validator
Enforces all README & PRD §10 rules and invariants across all 20 case JSON files.
"""

import os
import re
import json
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

VALID_PATTERNS = {
    "card_testing",
    "card_not_present_fraud",
    "card_not_present_new_device",
    "out_of_region_use",
    "account_takeover",
    "undocumented",
    "none"
}

VALID_ROUTES = {"auto", "L1", "L2"}
VALID_STATUSES = {"open", "closed_fraud", "closed_legitimate", "escalated"}
VALID_VERDICTS = {"fraud", "legitimate", "uncertain"}

def validate_case_json(file_path: str) -> List[str]:
    errors = []
    if not os.path.exists(file_path):
        return [f"File {file_path} does not exist."]

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [f"JSON syntax error in {file_path}: {e}"]

    # 1. Top level fields
    top_fields = ["case_id", "case", "evidence_requests", "next_best_actions", "sar", "stop_reason", "tool_calls", "tokens", "latency_s"]
    for tf in top_fields:
        if tf not in data:
            errors.append(f"Missing top-level field: {tf}")

    case_obj = data.get("case", {})
    sar_obj = data.get("sar", {})
    nba_obj = data.get("next_best_actions", {})

    # 2. Case fields
    case_fields = [
        "status", "verdict", "fraud_probability", "pattern", "pattern_description",
        "affected_txn_ids", "first_suspicious_txn_id", "connected_card_ids",
        "connected_device_profiles", "exposure_usd", "evidence", "similar_prior_cases",
        "summary", "written_to_graph", "graph_case_id"
    ]
    for cf in case_fields:
        if cf not in case_obj:
            errors.append(f"Missing case field: {cf}")

    if case_obj.get("status") not in VALID_STATUSES:
        errors.append(f"Invalid case status: {case_obj.get('status')}")

    verdict = case_obj.get("verdict")
    if verdict not in VALID_VERDICTS:
        errors.append(f"Invalid case verdict: {verdict}")

    pattern = case_obj.get("pattern")
    if pattern not in VALID_PATTERNS:
        errors.append(f"Invalid case pattern: {pattern}")

    if pattern == "undocumented" and not case_obj.get("pattern_description"):
        errors.append("pattern is undocumented but pattern_description is empty")

    if verdict == "legitimate":
        if len(case_obj.get("affected_txn_ids", [])) != 0:
            errors.append("verdict is legitimate but affected_txn_ids is not empty")
        if case_obj.get("exposure_usd", 0) != 0.0:
            errors.append("verdict is legitimate but exposure_usd is not 0")
        if sar_obj.get("file") is True:
            errors.append("verdict is legitimate but sar.file is true")

    # 3. SAR fields
    sar_fields = ["file", "reason", "narrative", "subjects", "total_amount_usd", "activity_dates"]
    for sf in sar_fields:
        if sf not in sar_obj:
            errors.append(f"Missing sar field: {sf}")

    final_actions = [a.get("action") for a in nba_obj.get("final", [])]
    has_file_report = "FILE_REPORT" in final_actions

    if sar_obj.get("file") != has_file_report:
        errors.append(f"sar.file ({sar_obj.get('file')}) must agree with FILE_REPORT in final actions ({has_file_report})")

    if sar_obj.get("file") is False:
        if sar_obj.get("narrative") != "":
            errors.append("sar.file is false but narrative is not empty string")
        if sar_obj.get("subjects") != []:
            errors.append("sar.file is false but subjects is not empty list")
        if sar_obj.get("total_amount_usd") != 0.0 and sar_obj.get("total_amount_usd") != 0:
            errors.append("sar.file is false but total_amount_usd is not 0")
        if sar_obj.get("activity_dates") != []:
            errors.append("sar.file is false but activity_dates is not empty list")
    else:
        # Check narrative sentence count (FinCEN requirement: 6 to 12 sentences)
        narrative = sar_obj.get("narrative", "")
        sentences = [s.strip() for s in re.split(r'[.!?]+', narrative) if s.strip()]
        if len(sentences) < 5 or len(sentences) > 15:
            errors.append(f"SAR narrative has {len(sentences)} sentences; expected 6-12 sentences.")

    # 4. Next Best Actions
    for category in ["initial", "final"]:
        for act in nba_obj.get(category, []):
            a_name = act.get("action")
            a_route = act.get("route")
            if a_name not in VALID_ACTIONS:
                errors.append(f"Invalid action name in {category}: {a_name}")
            if a_route not in VALID_ROUTES:
                errors.append(f"Invalid approval route in {category}: {a_route}")

            # Check exposure-dependent route on BLOCK_CARD
            if a_name == "BLOCK_CARD":
                exp = case_obj.get("exposure_usd", 0.0)
                expected_route = "L1" if exp <= 2500.0 else "L2"
                if a_route != expected_route:
                    errors.append(f"BLOCK_CARD route is {a_route} but exposure ${exp} requires {expected_route}")

    # 5. Tool calls and tokens
    if data.get("tool_calls", 0) <= 0:
        errors.append("tool_calls must be greater than 0")
    if data.get("tokens", 0) <= 0:
        errors.append("tokens must be greater than 0")
    if data.get("latency_s", 0.0) <= 0.0:
        errors.append("latency_s must be greater than 0.0")

    return errors

def validate_all_cases(cases_dir: str = "cases") -> Dict[str, List[str]]:
    results = {}
    total_errors = 0
    for i in range(1, 21):
        case_id = f"HHG-{i:03d}"
        file_path = os.path.join(cases_dir, f"{case_id}.json")
        errs = validate_case_json(file_path)
        results[case_id] = errs
        if errs:
            total_errors += len(errs)
            print(f"FAILED {case_id}: {errs}")
        else:
            print(f"PASSED {case_id}")
    print(f"\nValidation complete: {len(results)} cases evaluated, {total_errors} total errors.")
    return results

if __name__ == "__main__":
    validate_all_cases()
