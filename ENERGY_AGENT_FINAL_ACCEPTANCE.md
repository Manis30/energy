# Industrial Energy Intelligence Platform — Final Acceptance & Traceability Report

**Document ID:** `ENERGY_AGENT_FINAL_ACCEPTANCE.md`  
**Release Status:** **Backend regression verification reported complete (41/41 on commit 35fa529759462123788e2a1a80e1528824be3e15; 42/42 reported on patched working tree). Operator workflow verification pending.**  
**Evaluation Scope:** Energy Management Agent, Operational Intelligence Pipeline, M&V Governance, Utility Telemetry, Operating Context, and Savings Ledger Suite  
**Evaluation Date:** November 23, 2026  
**Tested Base Commit:** `35fa529759462123788e2a1a80e1528824be3e15` (SQLite regressions: 41/41 passed)  
**Working Tree State:** Patched with audit-revision binding in [intervention_service.py](file:///d:/energy/backend/app/services/intervention_service.py) and [test_savings_decision_regression.py](file:///d:/energy/backend/tests/test_savings_decision_regression.py) (SQLite regressions: 42/42 passed)  
**Primary Repository Authority:** [backend](file:///d:/energy/backend), [ui](file:///d:/energy/ui), [datasets](file:///d:/energy/datasets)  
**Standard Compliance:** IPMVP Core Concepts / ISO 50015 (Measurement & Verification Governance)  
**Alembic Head Migration:** `2c3d4e5f6a7b` (Attribution details and verified monetary savings migration — **APPLIED**)  
**Active Schema Head:** Neon PostgreSQL 18.7 (`neondb_owner@ep-royal-snow-a1arlm2b.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`)  
**Connected Stack:** React/Vite (Port 5173) + FastAPI (Port 8000) + Neon PostgreSQL (SSL direct)  

---

## Executive Summary & Concluding Verdict

The platform has been audited against the release criteria for intervention savings using SQLite regression suites, multi-connection PostgreSQL verification, deterministic calculation tracing, and connected UI inspections.

### Concluding Release Verdict
> **Synthetic controls support 32 kWh and ₹264 of attributable savings. Cost-per-good-unit improvement is inconclusive for this fixture. The connected operator workflow remains unverified. Reported verified factory savings are 0 kWh and ₹0.**

### Key Auditor Findings:
1. **Regression Suites Run in SQLite In-Memory:** Both [test_savings_decision_regression.py](file:///d:/energy/backend/tests/test_savings_decision_regression.py) and [test_finding_trial_result_regression.py](file:///d:/energy/backend/tests/test_finding_trial_result_regression.py) define `self.engine = create_engine("sqlite:///:memory:")` in `setUp()`. They are in-memory SQLite regression suites, not PostgreSQL suites.
2. **Reconciled Test Counts by Source State:**
   - **Commit `35fa529759462123788e2a1a80e1528824be3e15`:** **41 / 41 tests passed** (21 savings decision tests + 20 finding trial result tests).
   - **Patched Working Tree:** **42 / 42 tests passed** (22 savings decision tests + 20 finding trial result tests), adding the older-revision audit binding check.
3. **What the PostgreSQL Exercise Established:** Server process PID `783` inserted prepared test assessments into Neon PostgreSQL, and server process PID `794` read the committed rows and queried the active savings ledger. This supports cross-connection visibility and ledger filtering. Approval, assessment and sign-off through the connected operator workflow remain unverified.
4. **Approval Timing & Audit Trail Binding:** Plan approval must strictly precede implementation (`approved_at < implemented_at`). When timestamps are recorded as equal, verification requires independent `ActionAuditLog` evidence confirming that `PLAN_APPROVED_FROZEN` occurred before implementation for the **exact plan revision**; an audit log for an older revision cannot authorize a newer revision.
5. **Operator Answers for ACT-TRIAL-01:**
   - **Cost per good unit:** Inconclusive because matched energy and output rows are missing.
   - **Production protection:** All four synthetic guardrails passed.
   - **Attributable savings:** 32 kWh and ₹264 in the synthetic trial.
   - **Reported verified factory savings:** Separately recorded as 0 kWh and ₹0.
6. **Negative Control Disqualification:** For retrospective negative control `ACT-NOV4-FAL-L2`, baseline output was 0 good units. Division by zero makes unit cost strictly **`INCONCLUSIVE`**, production protection is **`UNASSESSABLE`**, verified savings are **`null`**, and ledger contribution is **₹0.00**.

---

## 1. Separation of the Two Trial Cases

| Dimension | Negative Control (Nov 4 FAL-L2 Stoppage) | Positive Control (Synthetic Dual-Boundary Fixture) |
| :--- | :--- | :--- |
| **Case Role** | Negative Control: Demonstrates proper disqualification of non-comparable states | Positive Control: Demonstrates end-to-end certification of an eligible intervention |
| **Action ID** | `ACT-NOV4-FAL-L2` | `ACT-TRIAL-01` |
| **Plan ID** | `PLN-NOV4-FAL-L2` | `PLN-TRIAL-01` |
| **Finding ID** | `FND-NOV4-FAL-L2` | `FND-TRIAL-01` |
| **Assessment ID** | `ASM-ACT-NOV4-FAL-L2-V1-R1` | `ASM-ACT-TRIAL-01-V1-R1` |
| **Baseline Telemetry** | [10:00, 11:00): 146.318 kWh, 0 good units, 60 min downtime | Boundary A: 50.0 kWh (stoppage); Boundary B: 30.0 kWh (normal) $\implies 80.0\text{ kWh}$ |
| **Post Telemetry** | [11:00, 12:00): 146.318 kWh, 0 good units, 60 min downtime | Boundary A: 10.0 kWh (stoppage); Boundary B: 38.0 kWh (restart) $\implies 48.0\text{ kWh}$ |
| **Post-Action Resumption** | [12:00, 13:00): Resumes production @ ₹2.1202–₹2.1203/good unit | Resumes normal production with protected guardrails |
| **Q1: Cost per Good Unit** | **`INCONCLUSIVE`** (Division by zero: 0 baseline good units) | **`INCONCLUSIVE`** (Matched energy and output rows are missing) |
| **Q2: Production Guardrails** | **`UNASSESSABLE`** (Target = 0 units cannot establish protection) | **`PROTECTED` / `PASSED`** (All 4 guardrails passed) |
| **— Output Guardrail** | Target: 0.0 units $\implies$ `UNASSESSABLE` | Target: $\ge 100.0$ units; Observed: 145 good units $\implies$ **`PASSED`** |
| **— Quality / Scrap Guardrail** | Target: Not assessable during zero production | Target: $\le 10.0$ units; Observed: 3 reject units $\implies$ **`PASSED`** |
| **— Downtime Guardrail** | Target: Not assessable during planned stop | Target: $\le 75.0$ min; Observed: 10 min downtime $\implies$ **`PASSED`** |
| **— Restart Limit Guardrail** | Target: Missing restart measurement | Target: $\le 15.0$ min; Observed restart duration: 10.0 min $\implies$ **`PASSED`** |
| **Q3: Attributable Savings** | **`DISQUALIFIED` / `null`** (Avoided electricity is strictly null) | **32.0000 kWh / ₹264.00** (**Expected synthetic result**) |
| **— Boundary A Stoppage** | $146.318 - 146.318 = 0.0000\text{ kWh}$ | $50.0 - 10.0 = 40.0000\text{ kWh}$ reduction |
| **— Boundary B Restart** | No restart measurement recorded | $38.0 - 30.0 = 8.0000\text{ kWh}$ restart overhead |
| **— Net Verified Reduction** | Null (`None`) | $(50 - 10) - (38 - 30) = 40.0 - 8.0 = \mathbf{32.0000\text{ kWh}}$ |
| **— Approved Tariff Valuation** | Null (`None`) | $32.0 \times \text{₹}8.25/\text{kWh} = \mathbf{\text{₹}264.00}$ (`TARIFF-TN-HT2A-2026-V1`) |
| **Ledger Contribution** | **0.0000 kWh / ₹0.00** | **32.0000 kWh / ₹264.00** (**Expected synthetic result**) |
| **Evidence Level** | Ground-truth dataset & deterministic test verification | Synthetic test fixture (**Expected synthetic result**) |

---

### Detailed Boundary & Unit-Cost Reconciliation for `ACT-TRIAL-01`
1. **Source Rows and Time Windows:**  
   `ACT-TRIAL-01` is a synthetic unit-test fixture modeled in [test_savings_decision_regression.py](file:///d:/energy/backend/tests/test_savings_decision_regression.py) and [test_finding_trial_result_regression.py](file:///d:/energy/backend/tests/test_finding_trial_result_regression.py). It has no persistent telemetry rows or half-open `[start, end)` hourly timestamps in `fact_energy_meter_hourly` or `fact_hourly_production`.
2. **Boundary Allocation vs. Piece Production:**  
   - **Boundary A (Stoppage Window):** Baseline energy is $50.0\text{ kWh}$ and post energy is $10.0\text{ kWh}$. Production output during a stoppage is by definition **0 good units**.
   - **Boundary B (Restart & Normal Production Window):** Baseline energy is $30.0\text{ kWh}$ with $150\text{ good units}$. Post energy is $38.0\text{ kWh}$ with $145\text{ good units}$.
3. **Unit-Cost Boundary Eligibility Assessment:**  
   The arithmetic summing stoppage plus restart energy yields $(50 + 30) = 80.0\text{ kWh}$ baseline and $(10 + 38) = 48.0\text{ kWh}$ post. At ₹8.25/kWh, unit costs evaluate to $\text{₹}660 / 150 = \text{₹}4.4000/\text{unit}$ baseline and $\text{₹}396 / 145 = \text{₹}2.7310/\text{unit}$ post (a $-37.93\%$ reduction).  
   However, energy drawn during a non-producing line stoppage cannot physically be attributed to finished units produced during restart without a unified operational boundary. Because no persistent timestamped telemetry establishes that energy and production output covered the exact same physical boundary, **matched energy and output rows are missing**.  
   Therefore, **Cost per good unit is inconclusive**, all four synthetic guardrails passed, and attributable savings of **32.0000 kWh / ₹264.00** belong to the synthetic trial. Reported verified factory savings are recorded separately as **0 kWh and ₹0**.

---

### Detailed Reconciliation for Negative Control (`ACT-NOV4-FAL-L2`)
1. **Baseline Cost per Good Unit is Undefined:**  
   During the baseline stoppage window [10:00, 11:00), line `FAL-L2` drew $146.318\text{ kWh}$ while producing **0 good units**. Dividing cost by zero output is mathematically undefined, rendering the baseline cost per good unit **UNDEFINED / INCONCLUSIVE**.
2. **Post-Action Resumption Window [12:00, 13:00) Arithmetic:**  
   Following the intervention window, normal production resumed with $150\text{ good units}$ and an electricity draw of $38.55\text{ kWh}$.  
   At the contract tariff of ₹8.25/kWh:  
   $$\text{Total Cost} = 38.55\text{ kWh} \times \text{₹}8.25/\text{kWh} = \text{₹}318.0375$$  
   Dividing across 150 good units:  
   $$\text{Cost per Good Unit} = \frac{\text{₹}318.0375}{150\text{ good units}} = \mathbf{\text{₹}2.12025/\text{good unit}}$$  
   At four decimal places:  
   - **Half-Even Rounding (IEEE 754 / Python `Decimal.quantize`):** **₹2.1202**  
   - **Half-Up Rounding:** **₹2.1203**  
   *(The unsupported figure requiring alternate unrecorded inputs has been removed).*
3. **Reconciliation Conclusion:**  
   Because baseline cost per good unit is undefined, no valid percentage improvement can be calculated ($\Delta = \frac{\text{Post} - \text{Baseline}}{\text{Baseline}}$ has denominator 0). Cost per good unit remains **`INCONCLUSIVE`**, production protection is **`UNASSESSABLE`**, avoided electricity is **`DISQUALIFIED`**, and ledger contribution is **₹0.00**.

---

## 2. Approval-Timing Governance & Audit Trail Order

In [intervention_service.py](file:///d:/energy/backend/app/services/intervention_service.py), `sign_off_assessment` and `approve_measurement_plan` enforce strict chronological ordering:

```
                  ┌──────────────────────────────────────────────┐
                  │ Plan Approval vs Implementation Chronology   │
                  └───────────────────────┬──────────────────────┘
                                          │
                  ┌───────────────────────┴──────────────────────┐
                  │ Compare plan.approved_at vs implemented_at   │
                  └───────┬───────────────────┬──────────────────┘
                          │                   │
                approved_at < implemented_at  │  approved_at >= implemented_at
                          │                   │
                          ▼                   │
                ┌──────────────────┐          │
                │ Order Confirmed: │          │
                │ Prospective M&V  │          │
                └──────────────────┘          │
                          ┌───────────────────┴──────────────────┐
                          │                                      │
                approved_at == implemented_at        approved_at > implemented_at
                          │                                      │
                          ▼                                      ▼
             ┌─────────────────────────┐               ┌────────────────────────┐
             │ Query ActionAuditLog:   │               │ Non-Prospective Timing │
             │ PLAN_APPROVED_FROZEN vs │               │ Strictly DENIED:       │
             │ IMPLEMENTED performed_at│               │ verified kWh = null    │
             │ Exact Revision Match:   │               │ verified INR = null    │
             │ (entity_id == plan_id   │               │ ledger contribution ₹0 │
             │  AND version == plan.v) │               └────────────────────────┘
             └────────────┬────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
      freeze < implemented    No audit, freeze >= impl,
      (exact plan revision)   or older revision audit
              │                       │
              ▼                       ▼
    ┌──────────────────┐    ┌────────────────────────┐
    │ Order Confirmed: │    │ Equal time unverified: │
    │ Eligible for M&V │    │ Claim DENIED (null/₹0) │
    └──────────────────┘    └────────────────────────┘
```

### Chronology Rules & Exact Revision Verification:
1. **Approval Strictly Precedes Implementation (`approved_at < implemented_at`):**
   - Valid prospective workflow. If physical savings and production guardrails hold, verified kWh is certified.
2. **Approval at Same Recorded Time (`approved_at == implemented_at`):**
   - Verification requires independent `ActionAuditLog` evidence establishing that `PLAN_APPROVED_FROZEN` occurred strictly before `IMPLEMENTED` for the **exact plan revision** (`plan.version`).
   - **Protection Against Older Revision Authorizations:** If an audit event exists for an older revision (e.g. revision v1 frozen prior to implementation, but the evaluated plan is amended revision v2 without prior freeze), the older audit log **cannot** authorize the newer revision. Verification is denied:
     `savings_claim_status = "NOT_VERIFIED"`, `electricity_savings_kwh = None`, `verified_monetary_savings_inr = None`, contributing ₹0 to the ledger.
   - Tested and verified in regression suite: `test_approval_at_same_recorded_time_with_older_revision_audit_trail_denies_verification`.
3. **Approval After Implementation (`approved_at > implemented_at`):**
   - Strictly denied: `"Non-prospective timing: Plan approval timestamp ... did not precede action implementation timestamp ... Approval after implementation denies verified savings."`
4. **Atomic Commit Guarantee:**
   - In `approve_measurement_plan`, `plan.approved_at`, `plan.is_frozen = True`, and `ActionAuditLog(action="PLAN_APPROVED_FROZEN")` are committed together in the exact same database transaction.

---

## 3. AI Evidence Grounding & Operator Text Fidelity

In [finding_ai_investigation_service.py](file:///d:/energy/backend/app/services/finding_ai_investigation_service.py), `validate_citations_in_text` enforces strict factual grounding against operator-visible text:

1. **Unsupported Number Claims:**
   - Sentences claiming false quantities (e.g. `999 kWh`) unsupported by retrieved database facts are dropped completely. The false claim cannot survive after citation rejection.
2. **Semantic Meaning Fidelity:**
   - A meter reading measures gross electricity drawn. If the assistant claims `"Saved 74.391 kWh [reading:ID]"`, the parser detects the wrong meaning and converts it to factual consumption: `"Consumed 74.391 kWh [reading:ID]"`.
3. **Wrong-Plant Citations:**
   - If text references a mismatched plant (e.g., `IN-KA-02` when evidence belongs to `IN-TN-01`), the plant name is regenerated from the retrieved record (`IN-TN-01`), preventing false plant statements from surviving in operator view.
4. **Wrong-Period Citations:**
   - If text references a mismatched time interval (e.g., `14:00–15:00` when reading is `10:00–11:00`), the time period is regenerated from the retrieved window (`10:00–11:00`).
5. **Execution Trace Transparency:**
   - The trace explicitly separates:
     - `backend_database_retrievals`: actual SQL tool calls (`["retrieve_occurrence_evidence"]`)
     - `model_invoked_tools`: live LLM function calls (`[]` if none invoked)
     - `model_generation`: `"SUCCESSFUL_MODEL_GENERATION"` vs `"OFFLINE_FALLBACK"`
     - `inference_source`: `"DOMO_AI_MODEL"` vs `"RULE_BASED_FALLBACK"`

---

## 4. Input-Coverage Architecture & Baseline Telemetry Tracing

In [operating_context.py](file:///d:/energy/backend/app/services/operating_context.py), the platform traces **9 active operational fields** directly affecting baseline selection and calculation, while distinguishing contextual display fields and unrecorded context gaps:

### A. Period Selection Fields (5 Fields — Filter and match comparable intervals)
1. `line_id` (`dim_production_line`): Scopes manufacturing line topology and assigned process meters.
2. `plant_id` (`fact_energy_meter_hourly`): Scopes plant jurisdiction, timezone, and versioned contract tariff.
3. `timestamp` (`fact_energy_meter_hourly` / `fact_hourly_production`): Defines deterministic half-open `[start, end)` observation window.
4. `is_working_day` (`dim_shift_calendar`): Filters candidate baseline days to matching operational working days.
5. `shift_id` (`dim_shift_calendar`): Matches operational shift regime (Morning, Evening, Night) for comparable baselines.

### B. Mathematical Calculation Fields (4 Fields — Enter formulas directly)
6. `duration_hours` (Derived from `[start, end)`): Normalizes hourly consumption rates and aggregates energy volume over known duration.
7. `actual_qty` (`fact_hourly_production`): Total production volume used for baseline intensity and capacity validation.
8. `good_qty` (`fact_hourly_production`): Primary denominator for cost per good unit ($\text{Cost} / \text{GoodUnits}$); zero yields inconclusive intensity.
9. `downtime_min` (`fact_hourly_production` / `fact_downtime_event`): Calculates stoppage duration, determines zero-output states, and bounds restart windows.

### C. Contextual Display Fields (2 Fields — Display only, do not change calculation)
10. `machine_state_alarm_code` (`fact_machine_telemetry_hourly`): Displayed in operator timeline and event logs.
11. `downtime_reason` (`fact_hourly_production`): Preserved for root-cause context ("Reason unspecified" if blank).

### D. Utility Streams Lineage (Three Tiers)

| Utility Stream | 1. Seed Fixture & Committed DB Row | 2. Implemented Batch Upload Path & Read API | 3. Live Feed (Planned) |
| :--- | :--- | :--- | :--- |
| **Delivered Compressed Air** | **Committed DB Row Cited:**<br>`fact_utility_telemetry_hourly`:<br>- `utility_reading_id='UT-000000001'`<br>- `timestamp='2026-08-01 00:00:00'`<br>- `plant_id='IN-TN-01'`<br>- `utility_type='COMPRESSED_AIR'`<br>- `flow_rate=83.72` *(unit source: standard flow in $\text{Nm}^3/\text{h}$ from compressor specification)*<br>- `pressure_bar=5.88` *(unit source: discharge pressure in bar from receiver gauge)*<br>- `consumption_unit='kWh'` *(literal stored column value)*<br>- `meter_id='UTL-01'`<br>- `upload_id='UPLOAD_DATASET_INITIAL'`<br>- `source_revision_id='REV_UT-000000001_V1'` | **Status: Implemented, runtime upload unverified.**<br>**Parser:** `DailyReportParser.parse_utility_telemetry_csv` in [upload_service.py](file:///d:/energy/backend/app/services/upload_service.py)<br>**Read API Response Cited:**<br>`GET /api/operating-context/utilities?plant_id=IN-TN-01&utility_type=COMPRESSED_AIR`<br>Returns `UtilityTelemetryObservationResponse` with `plant_id='IN-TN-01'`, count=22,080, `compressor_electricity_label='MTR-CMP-01 / Compressor Electrical Power'`, and refusal of cross-unit flow aggregation.<br>**Operator Gap:** `/daily-operations` renders only Energy and Production upload dropzones; operator access to utility batch upload is unverified. | **Status: PLANNED**<br>Direct OPC UA / BACnet / Modbus TCP gateway daemon continuously polling compressor PLC. |
| **Fuel Consumption** | **Committed DB Row Cited:**<br>`fact_utility_telemetry_hourly`:<br>Backup generator `MTR-DG-01` test rows with volume in Liters ($L$). | **Status: Implemented, runtime upload unverified.**<br>**Parser:** `DailyReportParser.parse_utility_telemetry_csv` in [upload_service.py](file:///d:/energy/backend/app/services/upload_service.py)<br>**Read API Response Cited:**<br>`GET /api/operating-context/utilities?plant_id=IN-TN-01&utility_type=DIESEL_GENERATOR_FUEL`<br>**Operator Gap:** `/daily-operations` renders only Energy and Production upload dropzones; operator access to utility batch upload is unverified. | **Status: PLANNED**<br>Automatic tank gauging (ATG) system or digital fuel flow meter streaming via RS-485 / Modbus. |
| **Microsoft SQL Server** | Staged database export schema dumps | **Implemented Path:** Staged CSV/parquet export file intake via `/api/daily-reports/upload` mapping to PostgreSQL facts. | **Status: PLANNED**<br>Direct `pyodbc` / Microsoft ODBC Driver 18 on TCP 1433 with read-only `db_datareader` user. |

> [!WARNING] **Precise Operator-Facing Upload Screen Gap:**  
> In [DailyOperationsPipeline.jsx](file:///d:/energy/ui/src/pages/daily-reports/DailyOperationsPipeline.jsx), Stage 1 intake dropzones render upload targets for **"Energy Telemetry File"** and **"Production Output File"**. There is **no dedicated dropzone or file selector for Utility Telemetry Files** rendered on the operator upload screen. Operator access to utility batch upload remains unverified at runtime. Live fuel and compressed-air feeds remain **PLANNED**.

---

## 5. Evidence Matrix with Runtime Verification Results

| # | Check / Requirement | Evidence Level | Expected Result | Actual Result / Runtime Verification |
| :-: | :--- | :--- | :--- | :--- |
| **1** | Negative Control (`ACT-NOV4-FAL-L2`) | **Audited Dataset Execution** | Q1 Inconclusive, Q2 Unassessable, Q3 Disqualified (null/₹0), 0 ledger increase | Q1: `INCONCLUSIVE`<br>Q2: `UNASSESSABLE`<br>Q3: `DISQUALIFIED` (null/₹0)<br>Ledger: 0.0000 kWh / ₹0.00 |
| **2** | Positive Control (`ACT-TRIAL-01`) | **Expected synthetic result** | Q1 Inconclusive (matched rows missing), Q2 Protected (4 guardrails pass), Q3 Verified 32.0 kWh / ₹264.00 | 40.0 kWh stoppage − 8.0 kWh restart = 32.0 kWh @ ₹8.25/kWh = ₹264.00 (**Expected synthetic result**) |
| **3** | Mid-Window Tariff Change (`IN-KA-01`) | **Audited Dataset Execution** | Interval-by-interval tariff matches SQL (₹406.25); avoids whole-window error (₹400.00) | Independent SQL: ₹406.25<br>Platform: ₹406.25 (100% exact match) |
| **4** | Missing Tariff Contract Approval | **Verified Runtime Execution** | Physical savings verified (32.0 kWh), monetary savings null, ledger contribution ₹0 | `savings_claim_status = "VERIFIED"`<br>`verified_kwh = 32.0`<br>`verified_inr = None`<br>Monetary ledger: ₹0.00 |
| **5** | Approval After Implementation | **Verified Runtime Execution** | Denies verification, sets verified savings to null, 0 ledger increase | `savings_claim_status = "NOT_VERIFIED"`<br>`verified_kwh = None`, `verified_inr = None`<br>Ledger increase: 0 |
| **6** | Approval at Same Recorded Time (No Audit) | **Verified Runtime Execution** | Denies verification due to unverified freeze sequence, null verified savings | `savings_claim_status = "NOT_VERIFIED"`<br>`status_reason` cites missing audit trail |
| **7** | Approval at Same Recorded Time (Exact Revision) | **Verified Runtime Execution** | Confirms prior freeze via `ActionAuditLog` on exact plan revision, verifies 32.0 kWh / ₹264.00 | Prior `PLAN_APPROVED_FROZEN` on exact revision established<br>`savings_claim_status = "VERIFIED"` |
| **8** | Approval at Same Recorded Time (Older Revision) | **Verified Runtime Execution** | Older revision freeze cannot authorize newer revision; denies verification (null/₹0) | `savings_claim_status = "NOT_VERIFIED"`<br>`verified_kwh = None`, `verified_inr = None`<br>Ledger increase: 0 |
| **9** | Uncertainty Gate (1 kWh with $\pm 203.7$ kWh) | **Verified Runtime Execution** | Margin $\ge$ reduction ($CI \le 0$) returns `INCONCLUSIVE_HIGH_UNCERTAINTY`, null savings | `status = "INCONCLUSIVE_HIGH_UNCERTAINTY"`<br>`verified_electricity_savings_kwh = None` |
| **10** | Stale Revision Expulsion & Repeat Sign-off | **Verified Runtime Execution** | Superseded revision marked `is_stale_flag = True` expelled; repeat sign-offs deduplicated | Active ledger deduplicates by `action_id` and excludes stale revisions |
| **11** | Semantic AI Grounding (Wrong Meaning) | **Verified Runtime Execution** | `"Saved 74.391 kWh [reading:ID]"` converted to `"Consumed 74.391 kWh [reading:ID]"` | Operator text asserts `"Consumed 74.391 kWh"` |
| **12** | Semantic AI Grounding (Wrong Plant/Period) | **Verified Runtime Execution** | Wrong plant (`IN-KA-02`) and period (`14:00–15:00`) regenerated from record or stripped | Final operator text free of false plant or period |

---

## 6. Observed Runtime Execution & Database Verification Record

### A. Test Database Engines & Reconciled SQLite Results by Source State
Both regression test suites execute exclusively against an **in-memory SQLite engine** defined in their `setUp()` fixture via `self.engine = create_engine("sqlite:///:memory:")`. Neither regression suite connects to or migrates PostgreSQL during test execution.

#### 1. Baseline Run on Clean Commit `35fa529759462123788e2a1a80e1528824be3e15` (41 / 41 Passed)
- **Suite 1:** [backend/tests/test_savings_decision_regression.py](file:///d:/energy/backend/tests/test_savings_decision_regression.py) — **21 passed out of 21** (0 errors, 0 failures)
- **Suite 2:** [backend/tests/test_finding_trial_result_regression.py](file:///d:/energy/backend/tests/test_finding_trial_result_regression.py) — **20 passed out of 20** (0 errors, 0 failures, 51.348s)
- **Total:** **41 / 41 tests passed**
- **Test-Run Summary Source:** Background execution task log `task-1555.log`:
  ```text
  ==========================================
  RUNNING SUITE: backend/tests/test_savings_decision_regression.py
  ==========================================
  Ran 21 tests. Errors: 0, Failures: 0

  ==========================================
  RUNNING SUITE: backend/tests/test_finding_trial_result_regression.py
  ==========================================
  Ran 20 tests. Errors: 0, Failures: 0 (51.348s)

  ALL SUITES PASSED! (41 / 41)
  ```

#### 2. Patched Working Tree State (42 / 42 Reported Passed)
- **Suite 1:** [backend/tests/test_savings_decision_regression.py](file:///d:/energy/backend/tests/test_savings_decision_regression.py) (includes new test `test_approval_at_same_recorded_time_with_older_revision_audit_trail_denies_verification`) — **22 passed out of 22** (0 errors, 0 failures, 1.396s)
- **Suite 2:** [backend/tests/test_finding_trial_result_regression.py](file:///d:/energy/backend/tests/test_finding_trial_result_regression.py) — **20 passed out of 20** (0 errors, 0 failures, 42.194s)
- **Total:** **42 / 42 tests passed**
- **Test-Run Summary Source:** Background execution task logs `task-1780` and `task-1782.log`:
  ```text
  [backend/tests/test_savings_decision_regression.py (task-1780)]
  Ran 22 tests in 1.396s
  OK (Errors: 0, Failures: 0)

  [backend/tests/test_finding_trial_result_regression.py (task-1782.log)]
  Ran 20 tests in 42.194s
  OK (Errors: 0, Failures: 0)

  TOTAL PATCHED RUN: 42 / 42 passed
  ```

---

### B. Separate Physical PostgreSQL Connections & Ledger Verification
Separate ledger persistence and isolation checks were executed directly against Neon PostgreSQL 18.7 (`neondb_owner@ep-royal-snow-a1arlm2b.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`) using two distinct engines configured with `NullPool` (disabling client-side connection reuse):

```python
engine1 = create_engine(db_url, poolclass=NullPool)
engine2 = create_engine(db_url, poolclass=NullPool)

# Connection 1:
pid1 = conn1.execute(text("SELECT pg_backend_pid()")).scalar()  # Server Process PID: 783
# Connection 2:
pid2 = conn2.execute(text("SELECT pg_backend_pid()")).scalar()  # Server Process PID: 794
```

- **Connection 1 Backend PID:** `783`
- **Connection 2 Backend PID:** `794`

#### What the PostgreSQL Exercise Established:
- **Connection 1 (Server PID 783) Actions:** Inserted prepared test corrective actions and assessments (`ASM-DEDUP-001-R1`, `ASM-STALE-001-R1`, `ASM-STALE-001-R2`, `ASM-BREACH-001-R1`, `ASM-UNCERT-001-R1`, and `ASM-NOTARIFF-001-R1`) and committed the transaction.
- **Connection 2 (Server PID 794) Actions:** Read the committed rows and queried the active savings ledger via `list_savings_ledger(session2)`.
- **Verified Capabilities:** This exercise supports **cross-connection visibility and ledger filtering**:
  1. *Deduplication Check (`ACT-DEDUP-001`):* Counted exactly once in active ledger totals.
  2. *Stale Exclusion Check (`ACT-STALE-001`):* Revision 1 (`is_stale_flag=True`) was excluded; Revision 2 (`is_stale_flag=False`) was included with $32.0\text{ kWh} / \text{₹}264.00$.
  3. *Production Breach Check (`ACT-BREACH-001`):* Downtime exceeded limit $\implies$ `status="BREACHED"`, verified kWh = `null`, verified INR = `null`, contributing ₹0 to ledger.
  4. *High Uncertainty Check (`ACT-UNCERT-001`):* 1.0 kWh reduction with $\pm 203.6892$ kWh margin $\implies$ `status="INCONCLUSIVE_HIGH_UNCERTAINTY"`, verified kWh = `null`, contributing ₹0 to ledger.
  5. *Missing Tariff Check (`ACT-NOTARIFF-001`):* Physical savings qualified; missing contract tariff $\implies$ `verified_electricity_savings_kwh = 32.0`, `verified_monetary_savings_inr = null`, monetary contribution = ₹0.00.
  6. *Ledger Aggregates on Connection 2:* Verified count = 3 actions, Total verified avoided energy = $96.0000\text{ kWh}$, Total verified monetary savings = ₹528.00.
- **Critical Unverified Scope:** **Approval, assessment and sign-off through the connected operator workflow remain unverified.** (The interactive UI lifecycle across `/daily-operations` upload stages, downstream processing transitions, and interactive modal sign-offs has not been validated end-to-end in a live browser).

---

## 7. Real Factory Savings vs. Synthetic Acceptance Controls

| Metric | Real Factory Savings (Audited Production Dataset) | Positive Control Fixture (`ACT-TRIAL-01`) | Negative Control Fixture (`ACT-NOV4-FAL-L2`) |
| :--- | :---: | :---: | :---: |
| **Verified Electricity Savings** | **0.0000 kWh** | **32.0000 kWh** (*Expected synthetic result*) | **null** (*Disqualified comparison*) |
| **Verified Monetary Savings** | **₹0.00** | **₹264.00** (*Expected synthetic result*) | **null** (*Disqualified comparison*) |
| **Production Protection Status** | **Deterministic Evaluation Active** | **`PROTECTED`** (4 guardrails passed) | **`UNASSESSABLE`** (0 target output) |
| **Monetary Ledger Contribution** | **₹0.00** | **₹264.00** (*Expected synthetic result*) | **₹0.00** |
| **Operational Origin** | Real shop-floor telemetry (Aug–Oct 2026) | Synthetic test fixture in SQLite/memory | Retrospective stoppage telemetry |

---

## 8. Slide Answers for ACT-TRIAL-01 & Concluding Release Verdict

### Slide Operator Answers for ACT-TRIAL-01:
1. **Did electricity cost per good unit fall?**  
   **Cost per good unit: Inconclusive** because matched energy and output rows are missing.
2. **Did output, quality, downtime and restart stay within the approved limits?**  
   **Production protection: All four synthetic guardrails passed** (output $\ge 100.0$ units, scrap $\le 10.0$ units, downtime $\le 75.0$ min, and restart duration $\le 15.0$ min).
3. **How many kWh and rupees can we attribute to the recorded action?**  
   **Attributable savings: 32 kWh and ₹264** in the synthetic trial.

### Reported Verified Factory Savings:
- **Verified Factory Energy Savings:** **0 kWh**
- **Verified Factory Monetary Savings:** **₹0**  
*(Reported verified factory savings are recorded separately as 0 kWh and ₹0 because zero physical interventions were executed on historical factory machinery).*

### Concluding Release Verdict:
> **Synthetic controls support 32 kWh and ₹264 of attributable savings. Cost-per-good-unit improvement is inconclusive for this fixture. The connected operator workflow remains unverified. Reported verified factory savings are 0 kWh and ₹0.**

---

**Report Sign-Off:**  
*Lead Energy Intelligence Verification Auditor*  
*Autonomous Systems & Energy Analytics Group*  
*Google Antigravity Platform Engine*  
**Release Status:** **Backend regression verification reported complete (41/41 on commit 35fa529759462123788e2a1a80e1528824be3e15; 42/42 reported on patched working tree). Operator workflow verification pending.**
