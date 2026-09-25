# Building an Autonomous GraphRAG Agent for Real-Time Fraud Investigation with TigerGraph

*How we built a hybrid AI copilot on TigerGraph, combining deep graph analytics, Bayesian reasoning, and multi-agent tool calling across 590,000+ transactions.*

---

## 1. The Challenge: Beyond Static Rules and Opaque Scores

Traditional fraud detection systems at major card issuers operate in extremes:
1. **Rigid Rule Filters:** Easily circumvented by evolving criminal syndicates.
2. **Machine Learning Risk Scores:** Provide numbers between `0.0` and `1.0` with zero interpretability. In practice, high model scores on new devices or travel locations are overwhelmingly **false alarms**, while coordinated syndicates intentionally keep individual transaction scores low to fly under the radar.

When investigating an alert, human fraud analysts don't just inspect the transaction amount; they examine **relational context**:
- *What is this cardholder's baseline velocity and modal billing region?*
- *Is this device shared with other cards across the network?*
- *Does this activity match known or emerging fraud topologies (card testing, structuring, anonymous proxy rings)?*
- *What regulatory filings (SARs) or cardholder blocks are warranted under issuer policy?*

For the **TigerGraph × Hacker House Goa (IEEE-CIS)** challenge, we designed and built an **Autonomous GraphRAG Fraud Investigation Agent**. Given 590,742 transactions, 144,432 identity profiles, and 5,565 historical closed cases, our system autonomously investigates alerts, queries graph topology in real time, formulates Bayesian probability assessments, enforces approval routing, and generates regulatory SARs.

---

## 2. Architecture: The 10-Step Investigation State Machine

Rather than relying on a loose LLM chat loop that hallucinates transaction numbers, our agent is structured around a rigorous **10-step autonomous state machine**:

```
 [Alert Intake] ──> [Baseline Establishment] ──> [Graph Expansion (Time/Device/Region)]
        │
        ▼
 [Pattern Detectors (R5, U1, U2)] ──> [Graph Memory Retrieval (Closed Cases)]
        │
        ▼
 [Bayesian Probability Update] ──> [Simulated Cardholder Verification]
        │
        ▼
 [Policy Decision (Rules R1-R10)] ──> [SAR Narrative Synthesis] ──> [Graph Write-Back]
```

### The 10 Lifecycle Steps:
1. **INTAKE (`t1_case_context`):** Loads the alert trigger (real-time risk score, customer dispute, or analyst tip), card ID, customer ID, and device identity.
2. **BASELINE (`t3_card_baseline`):** Computes statistical baselines across all historical activity (median transaction amount, 95th percentile, modal region, channel distribution).
3. **EXPAND (`t4_card_window`, `t7_region_history`):** Expands the temporal neighborhood $\pm 24$ hours around the event and compares geographical history against home regions.
4. **DETECT (`t10`, `t11`, `t12`):** Runs specialized topological detectors:
   - **Card Testing (Rule R5):** 3+ micro-authorizations ($<\$5$) within an hour followed by a larger purchase.
   - **Structuring (Undocumented Pattern U2):** Rapid bursts of transactions clustered within 10% below \$500 or \$1,000 limits.
   - **Anonymous Proxy Rings (Pattern U1):** Multi-card syndicates sharing hardware footprints behind anonymous proxies.
5. **RETRIEVE MEMORY (`t13_similar_closed_cases`):** Searches the 5,565 resolved historical cases (July–October) for matching structural signatures and prior analyst notes.
6. **ASSESS:** Computes an initial calibrated Bayesian fraud probability from evidence signals rather than raw model scores.
7. **REQUEST EVIDENCE (`EvidenceSimulator`):** Simulates customer verification under policy constraints when probability is ambiguous ($p < 0.70$).
8. **DECIDE (`PolicyEngine`):** Maps evidence to deterministic policy actions (Rules R1–R10) with mandatory approval routes (`auto`, `L1` Team Lead, `L2` Fraud Manager).
9. **EXPLAIN (`InvestigationExplainer`):** Synthesizes structured claims and drafts regulatory FinCEN-compliant SAR narratives (answering who, what, when, where, how, and why).
10. **PERSIST (`t15_write_case`):** Writes an `InvestigationCase` vertex back into TigerGraph, linking affected cards, devices, and transactions for future GraphRAG retrieval.

---

## 3. How We Leveraged TigerGraph

### A. Graph Schema Design
We modeled the fraud domain using a property graph schema optimized for multi-hop relational traversal:

```gsql
CREATE VERTEX Customer (PRIMARY_ID id STRING)
CREATE VERTEX Card (PRIMARY_ID id STRING, network STRING, card_type STRING)
CREATE VERTEX Transaction (PRIMARY_ID id INT, amt DOUBLE, ts DATETIME, risk_score DOUBLE)
CREATE VERTEX DeviceProfile (PRIMARY_ID profile_key STRING, is_proxy BOOL, rarity_score DOUBLE)
CREATE VERTEX BillingRegion (PRIMARY_ID region_code INT)
CREATE VERTEX InvestigationCase (PRIMARY_ID case_id STRING, verdict STRING, exposure DOUBLE)

CREATE UNDIRECTED EDGE OWNS_CARD (FROM Customer, TO Card)
CREATE UNDIRECTED EDGE USED_CARD (FROM Transaction, TO Card)
CREATE UNDIRECTED EDGE USED_DEVICE (FROM Transaction, TO DeviceProfile)
CREATE UNDIRECTED EDGE BILLED_IN (FROM Transaction, TO BillingRegion)
CREATE UNDIRECTED EDGE CITES_CASE (FROM InvestigationCase, TO Transaction)
```

### B. Why Graph Outperformed Relational Joins
- **Sub-Second Multi-Hop Traversal:** Detecting whether a card was part of an anonymous device syndicate required traversing:
  $$\text{Card}_A \longrightarrow \text{Transaction}_1 \longrightarrow \text{DeviceProfile} \longleftarrow \text{Transaction}_2 \longleftarrow \text{Card}_B$$
  In relational SQL over 590,000 rows, self-joining multiple tables with group-bys took seconds. In TigerGraph, this 2-hop neighborhood expansion executed in milliseconds.
- **Rarity Scoring via Accumulators:** Using GSQL accumulators (`SumAccum`, `SetAccum`), we calculated real-time device rarity scores across the entire ecosystem, instantly differentiating generic desktop browsers from rare mobile emulator profiles.
- **Dynamic Case Memory:** Writing resolved cases as vertices enabled immediate **Graph Memory Feedback**: case $\text{HHG-014}$ immediately cited cases $\text{CC-0141}$ and past device records created in the graph.

---

## 4. Engineering for Production: Overcoming LLM Rate Limits

During development, we connected our tool belt to frontier LLM APIs (Groq and Google Gemini) via a ReAct tool-calling loop. When testing multi-step investigations, we discovered that streaming accumulated graph context (590K transaction features, 15 tool schemas, and multi-turn payloads) frequently breached free-tier tokens-per-minute (TPM) and requests-per-minute (RPM) quotas.

### The Solution: A Resilient Hybrid Architecture
We engineered a **fail-safe dual-core architecture**:
1. **Interactive Conversational Mode (Gemini 3.5 / Flash Latest):** When an analyst asks exploratory questions (*"Compare HHG-001 and HHG-002"*, *"Simulate a what-if where the transaction was \$50"*), the agent uses the live LLM with function calling.
2. **Deterministic Graph State Machine Core:** The 10-step investigation logic runs on a deterministic, high-speed Python/TigerGraph engine. If API rate limits or quota drops occur, the agent gracefully falls back to deterministic expert rules—ensuring zero downtime, zero hallucinations, and 100% policy compliance.

---

## 5. Results & Benchmark Evaluation

We evaluated the autonomous agent across all **20 benchmark exam cases (`HHG-001` through `HHG-020`)** from `case_pack.csv`:

- **Schema & Policy Conformance:** **20 / 20 Cases PASSED (0 errors)** on the strict validator.
- **Calibrated False-Alarm Detection:** The agent correctly recognized that high model risk scores ($0.87 - 0.93$) on novel regions were traveling customers rather than cloned cards, correctly avoiding unnecessary customer card blocks under Rule R1 and R3.
- **Pattern Discovery:**
  - Accurately flagged **Card Testing (R5)** sequences (e.g. sub-\$3 authorizations followed by large purchases).
  - Detected the **Undocumented Anonymous Proxy Ring (U1)** across 52+ cards sharing `SM-G935F` Android profiles.
  - Identified **Structuring (U2)** clusters keeping authorizations just below \$500 limits.
- **Regulatory Precision:** Filed full FinCEN-compliant SAR narratives only when policy thresholds were met (exposures $>\$1,000$ or shared syndicates), achieving the calibrated ~8.5% reporting rate observed in historical truth.

---

## 6. Conclusion & What's Next

By unifying **TigerGraph's native topological speed** with **state-machine agentic workflows**, we demonstrated that fraud investigation AI agents can move beyond simplistic LLM wrappers. The result is an auditable, deterministic, and interactive fraud copilot that protects cardholders while dismantling complex organized syndicates.

- **GitHub Repository:** [https://github.com/Atharvkulshrestha08/HHGoa-Task-4](https://github.com/Atharvkulshrestha08/HHGoa-Task-4)
- **Live Analyst Dashboard:** Streamlit UI on local port `8501`.
- **License:** MIT License.
