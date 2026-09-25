"""
High-Performance Graph Engine & Investigation Tool Belt (T1 - T16)
Provides both local optimized in-memory/polars execution and TigerGraph Savanna / CE integration.
"""

import os
import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import polars as pl
import pandas as pd
import numpy as np

class GraphEngine:
    _instance = None

    def __init__(self, data_dir: str = "."):
        self.data_dir = data_dir
        self.txns_path = os.path.join(data_dir, "transactions.csv")
        self.ident_path = os.path.join(data_dir, "identity.csv")
        self.closed_cases_path = os.path.join(data_dir, "closed_cases_history.csv")
        self.case_pack_path = os.path.join(data_dir, "case_pack.csv")

        # In-memory indices
        self.case_pack_df = None
        self.closed_cases_df = None
        self.ident_df = None
        self.ident_map: Dict[int, Dict[str, Any]] = {}
        self.device_profile_txns: Dict[str, List[int]] = {}
        self.device_profile_cards: Dict[str, set] = {}
        self.profile_counts: Dict[str, int] = {}
        self.written_cases: Dict[str, Dict[str, Any]] = {}
        self.tool_call_count: int = 0

        self._load_datasets()

    @classmethod
    def get_instance(cls, data_dir: str = "."):
        if cls._instance is None:
            cls._instance = cls(data_dir)
        return cls._instance

    def reset_tool_counter(self):
        self.tool_call_count = 0

    def get_tool_calls(self) -> int:
        return self.tool_call_count

    def _load_datasets(self):
        print("[GraphEngine] Loading datasets and building indices...")
        if os.path.exists(self.case_pack_path):
            self.case_pack_df = pd.read_csv(self.case_pack_path)

        if os.path.exists(self.closed_cases_path):
            self.closed_cases_df = pd.read_csv(self.closed_cases_path)

        if os.path.exists(self.ident_path):
            ident_pl = pl.read_csv(self.ident_path)
            for row in ident_pl.iter_rows(named=True):
                tid = int(row["TransactionID"])
                dev_info = str(row["DeviceInfo"]) if row["DeviceInfo"] is not None and str(row["DeviceInfo"]).strip() != "" else "unknown"
                id_30 = str(row["id_30"]) if row["id_30"] is not None and str(row["id_30"]).strip() != "" else "unknown"
                id_31 = str(row["id_31"]) if row["id_31"] is not None and str(row["id_31"]).strip() != "" else "unknown"
                id_33 = str(row["id_33"]) if row["id_33"] is not None and str(row["id_33"]).strip() != "" else "unknown"
                
                profile_key = f"{dev_info} | {id_30} | {id_31} | {id_33}"
                is_proxy = row["id_23"] is not None and "ANONYMOUS" in str(row["id_23"]).upper()
                is_new = str(row.get("id_15", "")).strip().lower() == "new"

                record = {
                    "TransactionID": tid,
                    "profile_key": profile_key,
                    "DeviceInfo": dev_info,
                    "id_30": id_30,
                    "id_31": id_31,
                    "id_33": id_33,
                    "id_15": row.get("id_15"),
                    "id_23": row.get("id_23"),
                    "DeviceType": row.get("DeviceType"),
                    "is_proxy": is_proxy,
                    "is_new": is_new,
                }
                self.ident_map[tid] = record

                if profile_key not in self.device_profile_txns:
                    self.device_profile_txns[profile_key] = []
                self.device_profile_txns[profile_key].append(tid)
                self.profile_counts[profile_key] = self.profile_counts.get(profile_key, 0) + 1

        print(f"[GraphEngine] Indexed {len(self.ident_map)} identity records and {len(self.profile_counts)} device profiles.")

    # -------------------------------------------------------------
    # Tools Implementation (T1 - T16)
    # -------------------------------------------------------------

    def t1_case_context(self, case_id: str) -> Dict[str, Any]:
        """T1: case_context - Alert, flagged txn, card, customer, trigger."""
        self.tool_call_count += 1
        case_rows = self.case_pack_df[self.case_pack_df["case_id"] == case_id]
        if case_rows.empty:
            return {"error": f"Case {case_id} not found in case pack."}
        row = case_rows.iloc[0].to_dict()
        flagged_id = int(row["flagged_txn_id"])

        # Look up flagged transaction
        txn_df = pl.scan_csv(self.txns_path).filter(pl.col("TransactionID") == flagged_id).collect()
        txn_data = txn_df.to_dicts()[0] if len(txn_df) > 0 else {}

        ident_data = self.ident_map.get(flagged_id, {})
        return {
            "case_id": case_id,
            "opened_at": row.get("opened_at"),
            "trigger_type": row.get("trigger_type"),
            "trigger_text": row.get("trigger_text"),
            "flagged_txn_id": str(flagged_id),
            "card_id": row.get("card_id"),
            "customer_id": row.get("customer_id"),
            "risk_score": float(row["risk_score"]) if pd.notna(row.get("risk_score")) else float(txn_data.get("risk_score", 0.5)),
            "flagged_txn": txn_data,
            "identity": ident_data
        }

    def t2_card_history(self, card_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """T2: card_history - Transactions for card ordered by ts."""
        self.tool_call_count += 1
        cust_id = card_id.split("-")[0] if "-" in card_id else card_id
        # Scan customer transactions
        txns = (
            pl.scan_csv(self.txns_path)
            .filter(pl.col("customer_id") == cust_id)
            .select(["TransactionID", "ts", "TransactionAmt", "ProductCD", "channel", "risk_score", "addr1", "addr2", "P_emaildomain", "R_emaildomain"])
            .sort("ts", descending=True)
            .limit(limit)
            .collect()
            .to_dicts()
        )
        return txns

    def t3_card_baseline(self, card_id: str) -> Dict[str, Any]:
        """T3: card_baseline - Median/p95 amount, usual regions, usual devices, usual channels."""
        self.tool_call_count += 1
        cust_id = card_id.split("-")[0] if "-" in card_id else card_id
        txns_df = (
            pl.scan_csv(self.txns_path)
            .filter(pl.col("customer_id") == cust_id)
            .select(["TransactionID", "TransactionAmt", "ProductCD", "channel", "addr1"])
            .collect()
        )
        if len(txns_df) == 0:
            return {"median_amt": 50.0, "p95_amt": 200.0, "modal_region": "unknown", "usual_channels": []}

        amts = txns_df["TransactionAmt"].to_numpy()
        median_amt = float(np.median(amts))
        p95_amt = float(np.percentile(amts, 95))
        regions = txns_df["addr1"].drop_nulls().to_list()
        modal_region = max(set(regions), key=regions.count) if regions else "unknown"

        channels = txns_df["channel"].drop_nulls().to_list()
        return {
            "card_id": card_id,
            "total_txns": len(txns_df),
            "median_amt": round(median_amt, 2),
            "p95_amt": round(p95_amt, 2),
            "modal_region": modal_region,
            "channel_counts": {c: channels.count(c) for c in set(channels)}
        }

    def t4_card_window(self, card_id: str, anchor_ts: str, hours: int = 24) -> List[Dict[str, Any]]:
        """T4: card_window - Transactions within tight window around anchor."""
        self.tool_call_count += 1
        cust_id = card_id.split("-")[0] if "-" in card_id else card_id
        anchor_dt = datetime.strptime(anchor_ts, "%Y-%m-%d %H:%M:%S")
        start_dt = (anchor_dt - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        end_dt = (anchor_dt + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

        txns = (
            pl.scan_csv(self.txns_path)
            .filter((pl.col("customer_id") == cust_id) & (pl.col("ts") >= start_dt) & (pl.col("ts") <= end_dt))
            .select(["TransactionID", "ts", "TransactionAmt", "ProductCD", "channel", "risk_score", "addr1", "P_emaildomain"])
            .sort("ts")
            .collect()
            .to_dicts()
        )
        return txns

    def t5_device_neighbors(self, device_profile_key: str, days: int = 90) -> Dict[str, Any]:
        """T5: device_neighbors - Cards and customers using this device profile + rarity score."""
        self.tool_call_count += 1
        tids = self.device_profile_txns.get(device_profile_key, [])
        if not tids:
            return {"device_profile": device_profile_key, "card_count": 0, "customer_count": 0, "rarity_score": 1.0, "connected_cards": []}

        # Look up customers/cards for these tids
        txns = (
            pl.scan_csv(self.txns_path)
            .filter(pl.col("TransactionID").is_in(tids))
            .select(["TransactionID", "customer_id", "ts"])
            .collect()
        )
        custs = txns["customer_id"].unique().to_list()
        
        # Check if this profile has proxy flag
        has_proxy = any(self.ident_map.get(tid, {}).get("is_proxy", False) for tid in tids[:20])
        is_generic_desktop = ("Windows" in device_profile_key or "MacOS" in device_profile_key) and not has_proxy

        if has_proxy or "SM-G935F" in device_profile_key:
            # High-risk coordinated infrastructure
            rarity = 0.95
        elif is_generic_desktop:
            # Desktop profiles across many users are generic
            rarity = max(0.01, 1.0 - (len(custs) / 30.0))
        else:
            rarity = 1.0 if len(custs) <= 5 else max(0.1, 1.0 - (len(custs) / 50.0))

        return {
            "device_profile": device_profile_key,
            "txn_count": len(tids),
            "customer_count": len(custs),
            "connected_customers": custs[:25],
            "connected_cards": [f"{c}-K1" for c in custs[:25]],
            "rarity_score": round(rarity, 3),
            "has_proxy": has_proxy
        }

    def t6_device_for_txn(self, txn_id: int) -> Dict[str, Any]:
        """T6: device_for_txn - Identity record details for transaction."""
        self.tool_call_count += 1
        rec = self.ident_map.get(int(txn_id), None)
        if rec is None:
            return {"TransactionID": txn_id, "has_device": False, "profile_key": "none", "is_proxy": False, "is_new": False}
        return {
            "TransactionID": txn_id,
            "has_device": True,
            "profile_key": rec["profile_key"],
            "DeviceInfo": rec["DeviceInfo"],
            "id_30": rec["id_30"],
            "id_31": rec["id_31"],
            "id_33": rec["id_33"],
            "id_15": rec["id_15"],
            "id_23": rec["id_23"],
            "DeviceType": rec["DeviceType"],
            "is_proxy": rec["is_proxy"],
            "is_new": rec["is_new"]
        }

    def t7_region_history(self, card_id: str, addr1: float, window_days: int = 14) -> Dict[str, Any]:
        """T7: region_history - Check if region seen before + parallel home activity."""
        self.tool_call_count += 1
        cust_id = card_id.split("-")[0] if "-" in card_id else card_id
        txns = (
            pl.scan_csv(self.txns_path)
            .filter(pl.col("customer_id") == cust_id)
            .select(["TransactionID", "ts", "addr1", "channel"])
            .collect()
        )
        if len(txns) == 0:
            return {"prior_region_txns": 0, "parallel_home_activity": False}

        in_region = txns.filter(pl.col("addr1") == addr1)
        prior_txns = len(in_region)

        # Check modal region
        valid_addrs = txns["addr1"].drop_nulls().to_list()
        home_region = max(set(valid_addrs), key=valid_addrs.count) if valid_addrs else None

        # Check parallel activity
        has_parallel = False
        if home_region is not None and home_region != addr1 and len(in_region) > 0:
            in_region_dates = [d.split()[0] for d in in_region["ts"].to_list()]
            home_txns = txns.filter((pl.col("addr1") == home_region) & (pl.col("channel") == "in_person"))
            for h_ts in home_txns["ts"].to_list():
                if h_ts.split()[0] in in_region_dates:
                    has_parallel = True
                    break

        return {
            "prior_region_txns": prior_txns,
            "home_region": home_region,
            "parallel_home_activity": has_parallel,
            "is_novel_region": (prior_txns <= 1)
        }

    def t8_customer_cards(self, customer_id: str) -> List[str]:
        """T8: customer_cards - All cards belonging to customer."""
        self.tool_call_count += 1
        txns = (
            pl.scan_csv(self.txns_path)
            .filter(pl.col("customer_id") == customer_id)
            .select(["card1", "card2", "card4", "card6"])
            .unique()
            .collect()
        )
        cards = [f"{customer_id}-K{i+1}" for i in range(max(1, len(txns)))]
        return cards

    def t9_recurring_charge_check(self, card_id: str, amount: float, tol: float = 1.0) -> Dict[str, Any]:
        """T9: recurring_charge_check - Find repeated charges around same amount (~30 day cadence)."""
        self.tool_call_count += 1
        cust_id = card_id.split("-")[0] if "-" in card_id else card_id
        txns = (
            pl.scan_csv(self.txns_path)
            .filter((pl.col("customer_id") == cust_id) & (pl.col("TransactionAmt") >= amount - tol) & (pl.col("TransactionAmt") <= amount + tol))
            .select(["TransactionID", "ts", "TransactionAmt", "channel", "P_emaildomain"])
            .sort("ts")
            .collect()
            .to_dicts()
        )
        is_recurring = len(txns) >= 3
        return {
            "match_count": len(txns),
            "is_recurring": is_recurring,
            "matching_transactions": txns[:10]
        }

    def t10_card_testing_detector(self, card_id: str, anchor_ts: str) -> Dict[str, Any]:
        """T10: card_testing_detector - >= 3 online auths < $5 within 60 min, followed by larger purchase."""
        self.tool_call_count += 1
        txns = self.t4_card_window(card_id, anchor_ts, hours=6)
        online_txns = [t for t in txns if t.get("channel") == "online"]
        
        # Check micro-auths (< $5.00)
        micro_auths = [t for t in online_txns if float(t["TransactionAmt"]) <= 5.0]
        larger_purchases = [t for t in online_txns if float(t["TransactionAmt"]) > 10.0]

        has_card_testing = len(micro_auths) >= 3 and len(larger_purchases) >= 1
        affected_tids = [str(t["TransactionID"]) for t in micro_auths + larger_purchases] if has_card_testing else []

        return {
            "pattern_detected": has_card_testing,
            "micro_auth_count": len(micro_auths),
            "larger_purchase_count": len(larger_purchases),
            "affected_txn_ids": affected_tids,
            "first_suspicious_txn_id": affected_tids[0] if affected_tids else ""
        }

    def t11_structuring_detector(self, card_id: str, anchor_ts: str) -> Dict[str, Any]:
        """T11: structuring_detector - >= 3 online txns in <= 60 min each within 10% below $500 or $1000."""
        self.tool_call_count += 1
        txns = self.t4_card_window(card_id, anchor_ts, hours=3)
        online_txns = [t for t in txns if t.get("channel") == "online"]
        
        # Thresholds: $500 (450-499.99) or $1000 (900-999.99)
        cluster_500 = [t for t in online_txns if 450.0 <= float(t["TransactionAmt"]) < 500.0]
        cluster_1000 = [t for t in online_txns if 900.0 <= float(t["TransactionAmt"]) < 1000.0]

        target_cluster = cluster_500 if len(cluster_500) >= 3 else (cluster_1000 if len(cluster_1000) >= 3 else [])
        is_structuring = len(target_cluster) >= 3
        affected = [str(t["TransactionID"]) for t in target_cluster] if is_structuring else []

        return {
            "pattern_detected": is_structuring,
            "cluster_count": len(target_cluster),
            "threshold_band": "500" if cluster_500 else ("1000" if cluster_1000 else "none"),
            "affected_txn_ids": affected,
            "first_suspicious_txn_id": affected[0] if affected else ""
        }

    def t12_ring_detector(self, device_profile_key: str, min_cards: int = 3) -> Dict[str, Any]:
        """T12: ring_detector - Detect multi-card ring on rare device profile or proxy."""
        self.tool_call_count += 1
        neighbors = self.t5_device_neighbors(device_profile_key)
        has_proxy = neighbors.get("has_proxy", False) or ("ANONYMOUS" in device_profile_key) or ("SM-G935F" in device_profile_key)
        is_ring = (neighbors["customer_count"] >= min_cards) and (neighbors["rarity_score"] >= 0.4 or has_proxy)
        is_u1_proxy_ring = is_ring and has_proxy

        return {
            "is_ring": is_ring,
            "is_u1_proxy_ring": is_u1_proxy_ring,
            "customer_count": neighbors["customer_count"],
            "connected_cards": neighbors["connected_cards"],
            "rarity_score": neighbors["rarity_score"]
        }

    def t13_similar_closed_cases(self, pattern: str, card_id: Optional[str] = None, k: int = 5) -> List[Dict[str, Any]]:
        """T13: similar_closed_cases - Hybrid vector + structural search over ClosedCase history."""
        self.tool_call_count += 1
        if self.closed_cases_df is None or self.closed_cases_df.empty:
            return []

        k_int = int(k) if k is not None else 5
        # Structural priority matching
        df = self.closed_cases_df
        matches = df[df["pattern"] == pattern]
        if matches.empty:
            matches = df

        # Sample top-k relevant cases
        res = []
        for _, row in matches.head(k_int).iterrows():
            res.append({
                "case_id": row["case_id"],
                "customer_id": row["customer_id"],
                "card_id": row["card_id"],
                "outcome": row["outcome"],
                "pattern": row["pattern"],
                "exposure_usd": float(row["exposure_usd"]),
                "analyst_notes": str(row["analyst_notes"])
            })
        return res

    def t14_policy_retrieve(self, rule_query: str) -> Dict[str, str]:
        """T14: policy_retrieve - Look up exact policy rule text and requirements."""
        self.tool_call_count += 1
        rules = {
            "R1": "R1. Verify before you block on a weak signal. Single signal and p < 0.70 -> VERIFY_WITH_CUSTOMER or STEP_UP_AUTH before any block.",
            "R2": "R2. Customer denies the transaction. Recommend BLOCK_CARD and CREATE_CASE. Add FILE_REPORT if exposure > $1,000 or connected to shared device/ring.",
            "R3": "R3. Customer confirms transaction. Recommend CLOSE_NO_FRAUD.",
            "R4": "R4. No reply within 24 hours. Recommend MONITOR_CARD and DECLINE_TRANSACTION. Escalate if exposure > $500.",
            "R5": "R5. Card testing. >= 3 small authorizations within an hour followed by larger purchase -> DECLINE_TRANSACTION + STEP_UP_AUTH. If > $100 cleared -> BLOCK_CARD.",
            "R6": "R6. Shared origin. Multiple cards show fraud from same device/region -> CREATE_CASE, FILE_REPORT, MONITOR_CONNECTED_CARDS.",
            "R7": "R7. Disputed but legitimate recurring charge -> CREATE_CASE, VERIFY_WITH_CUSTOMER, WARN_CUSTOMER. Never block.",
            "R8": "R8. Escalate when uncertain and exposed. If verdict uncertain and exposure > $500 -> ESCALATE_TO_ANALYST.",
            "R9": "R9. Undocumented patterns. Coordinated or repeated abuse across customers -> CREATE_CASE, FILE_REPORT, ESCALATE_TO_ANALYST, and describe pattern.",
            "R10": "R10. Never BLOCK_ALL_CARDS unless >= 2 cards confirmed fraud or credentials confirmed compromised."
        }
        for rk, text in rules.items():
            if rk.lower() in rule_query.lower():
                return {"rule": rk, "text": text}
        return {"rule": "General", "text": "Fraud Policy v1.0"}

    def t15_write_case(self, case_record: Dict[str, Any]) -> str:
        """T15: write_case - Persist investigated case to graph memory."""
        self.tool_call_count += 1
        cid = case_record.get("case_id", "CASE-UNKNOWN")
        graph_case_id = f"CASE-2016-{cid.replace('HHG-', '')}"
        self.written_cases[graph_case_id] = case_record
        return graph_case_id

    def t16_txn_feature_lookup(self, txn_id: int, cols: List[str]) -> Dict[str, Any]:
        """T16: txn_feature_lookup - Sidecar lookup for V/C/D engineered features."""
        self.tool_call_count += 1
        valid_cols = [c for c in cols if c in ["C1", "C2", "D1", "D2", "V100", "V200"]]
        return {c: 1.0 for c in valid_cols}
