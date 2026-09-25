"""
Batch Investigation Runner
Executes the TigerGraph Agentic Fraud Investigation on all 20 exam cases in case_pack.csv.
Outputs results to cases/<case_id>.json and validates schema conformance.
"""

import os
import sys
import json
import time

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.orchestrator import InvestigationOrchestrator
from src.eval.validator import validate_all_cases

def main():
    cases_dir = "cases"
    os.makedirs(cases_dir, exist_ok=True)
    
    print("=" * 70)
    print("Starting TigerGraph Fraud Investigation Agent on 20 Exam Cases")
    print("=" * 70)

    orchestrator = InvestigationOrchestrator(data_dir=".")
    total_start = time.time()
    
    for i in range(1, 21):
        case_id = f"HHG-{i:03d}"
        case_start = time.time()
        print(f"\n[Case {case_id}] Initiating autonomous investigation...")
        
        try:
            result = orchestrator.investigate_case(case_id)
            out_file = os.path.join(cases_dir, f"{case_id}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            
            verdict = result["case"]["verdict"]
            prob = result["case"]["fraud_probability"]
            exp = result["case"]["exposure_usd"]
            pattern = result["case"]["pattern"]
            dur = time.time() - case_start
            print(f"[Case {case_id}] Finished in {dur:.2f}s | Verdict: {verdict.upper()} | Prob: {prob} | Exposure: ${exp:,.2f} | Pattern: {pattern}")
        except Exception as e:
            print(f"[Case {case_id}] ERROR: {e}")

    total_time = time.time() - total_start
    print("\n" + "=" * 70)
    print(f"All 20 cases investigated in {total_time:.2f} seconds.")
    print("Running strict Answer Format validation...")
    print("=" * 70)

    val_results = validate_all_cases(cases_dir)
    return val_results

if __name__ == "__main__":
    main()
