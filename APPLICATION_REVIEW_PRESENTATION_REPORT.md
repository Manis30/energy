# Energy Intel — End-to-End Application Review

## Presentation-ready overview

### 1. What the application is

Energy Intel is an industrial energy and production intelligence application for factory teams. It brings hourly energy-meter readings and production records together so plant managers, energy engineers, and production leads can review energy use, production output, energy intensity, data quality, anomalies, and follow-up work in one place.

The central business question is:

> **Where is the plant consuming energy, what production and operating conditions coincide with that consumption, which signals need investigation, and has the follow-up been recorded?**

It is a monitoring, analysis, investigation, and workflow-support application. It is not a plant-control system: the reviewed implementation does not directly control equipment or prove that a detected signal has a specific physical cause.

### 2. Manufacturing context and problems this addresses

Typical manufacturing environments collect information across energy meters, line/shift reports, spreadsheets, MES/ERP systems, and maintenance processes. Across plants, common operational difficulties include:

- **Fragmented data:** energy readings and production quantities live in separate systems or files, making comparisons slow and error-prone.
- **Late visibility:** daily or shift reporting can delay recognition of unusual energy consumption or poor power factor.
- **Weak normalization:** total kWh alone does not show energy per board or finished unit; process meters and production quantities need the right time, plant, and process alignment.
- **Manual data quality checks:** inconsistent headers, missing periods, duplicates, and mismatched timestamps can undermine reports.
- **Alert fatigue and uncertain causes:** a threshold breach can be mistaken for an equipment fault or a confirmed saving opportunity.
- **Unclear ownership and closure:** investigation notes, recommendations, maintenance tasks, and evidence of resolution may be disconnected.
- **Hard-to-audit decisions:** teams need to know which source records and calculations support a reported number.

These are common industry patterns, not a claim that every manufacturer has the same systems or problems. The application addresses the data-to-investigation workflow; value depends on the accuracy and coverage of the plant's source data.

### 3. How Energy Intel addresses them

1. **Bring data into a consistent workflow:** upload daily energy and production CSV/XLS/XLSX reports, inspect and validate them, then ingest accepted data.
2. **Preserve lineage:** ingested records carry upload provenance so operational data can be traced to its report batch.
3. **Check source alignment:** compare energy and production coverage and surface reconciliation issues before relying on analysis.
4. **Calculate consistent metrics:** use backend calculations for energy, cost, emissions, production rates, process SEC, and factory SEC.
5. **Surface signals with caveats:** run four deterministic anomaly detectors, show baseline confidence, and distinguish an alert from a verified fault or avoidable waste.
6. **Create a traceable response path:** synchronize signals into findings, link recommendations and corrective actions, and retain lifecycle audit events.
7. **Support natural-language exploration:** the AI assistant selects analytical tools, retrieves their results, and exposes evidence/claim-verification information with its answer.

## 4. End-to-end operating workflow

The implemented Daily Operations page and backend pipeline use **eight stages**:

| Stage | What happens |
|---|---|
| 1. Data upload | Select the reporting date/plant and upload energy and/or production reports. |
| 2. Validation | Inspect file format and schema; validate columns, values, dates, duplicates, and references before ingestion. |
| 3. Database ingestion | Import validated records transactionally into PostgreSQL and associate them with upload history/provenance. Supports incremental ingestion and overwrite correction modes. |
| 4. Data reconciliation | Compare source coverage and cross-source alignment; expose duplicates or data-integrity warnings. |
| 5. Daily analytics | Retrieve energy, production, process-intensity, and factory-intensity calculations for the reporting scope. |
| 6. Intelligence report | Assemble the daily metrics and context into an operational summary. |
| 7. Anomaly detection | Run statistical, rolling-baseline, power-factor, and zero-production energy detectors. |
| 8. Investigation handoff | Map anomaly signals into persistent findings for review and follow-up. |

Pipeline states are shown per selected reporting date, with completed, warning, failed, blocked, and not-started states. This makes the upload-to-investigation sequence visible instead of hiding it behind a single dashboard number.

## 5. Agents and their responsibilities

### Important distinction

The implementation has **one conversational ReAct AI agent**, a set of deterministic analytics tools, and a deterministic numeric-evidence verification module. The verification module is code, **not a separate autonomous AI agent**. Likewise, the anomaly detectors and pipeline stages are services, not AI agents.

### Main assistant flow

1. The user asks a question in natural language.
2. Pure conversational greetings are handled deterministically. Analytical questions go to the ReAct agent.
3. The model chooses a registered tool and supplies arguments in a constrained JSON action format.
4. The backend validates the arguments and executes the tool against application data. The agent can make at most **five tool calls per turn**.
5. The model forms an answer from the returned results; successful tool executions are retained as evidence.
6. A deterministic verifier compares applicable numerical claims against successful tool results, including metric, units, date, and plant/meter/line/product scope.
7. The API returns the answer, tool references, sanitized evidence summaries, and claim-verification results.

The assistant does not own the authoritative calculations. The backend tools do. If a number or required scope is unavailable, the intended behavior is to report it as unavailable rather than invent or treat it as zero.

### Tool groups and responsibilities

The registry provides **21 tools**:

- **5 energy tools:** energy summary, meter breakdown, area breakdown, daily trend, and power-factor summary.
- **6 production tools:** overall summary, line, product, shift, downtime-by-reason, and daily trend.
- **4 energy-intensity tools:** process SEC, factory SEC, product process energy, and energy during zero-production periods.
- **5 anomaly tools:** statistical Z-score, rolling baseline, low power factor, zero-production standby, and a unified detector suite.
- **1 read-only SQL tool:** for supported analytical questions not directly covered by a named tool. It uses a read-only database role, SQL validation, a five-second query timeout, and a 100-row response limit.

The AI provider used by the assistant is Domo Text Generation API, configured through application settings. The client has bounded retries for transient errors; credentials belong in environment/secret configuration, not in presentation material.

### Finding, recommendation, and action responsibilities

- **Finding lifecycle:** persist and group operational signals with source measurements, occurrences, provenance, and status history.
- **Recommendation lifecycle:** create evidence-linked next-step guidance from a finding, apply status/priority rules, prevent duplicate active recommendations in the same finding/category, and record audit events. Recommendations do **not** make up savings or payback values.
- **Corrective-action lifecycle:** let a team record a task, owner attribution, due date, progress, and resolution notes. Completing a task does not automatically prove that the finding is resolved or the energy benefit was achieved.

## 6. What each application page does

The main navigation has seven workspace pages; Platform Story is an additional walkthrough linked from the sidebar footer.

| Page / route | Purpose and main content |
|---|---|
| **Dashboard** `/` | Executive summary of plant energy and production KPIs, intensity, charts, operational-health context, and items needing attention. It is the high-level starting point, not the place to establish root cause. |
| **Daily Operations** `/daily-operations` | The upload, validation, ingestion, reconciliation, analytics, daily report, anomaly, and handoff pipeline. Also exposes report history/audit context and stage-level results. |
| **Energy Analytics** `/energy-analytics` | Filter and inspect energy totals and trends, meter and area contribution, cost and CO2e context, power factor, and energy-versus-production/intensity context. Includes a clearly labeled hypothetical flat-rate tariff scenario. |
| **Production Analytics** `/production-analytics` | Review target and actual output, quality/reject/rework measures, production trends by line/product/shift, and logged downtime reasons/minutes. It does not derive OEE from fields that are not available. |
| **Investigation & Actions Centre** `/investigation-actions` | Unified workspace with tabs for findings/investigation, recommendations directory, corrective-action tracker, and live anomaly surveillance. Users can inspect finding evidence/occurrences/audit history, synchronize anomaly signals, and manage linked follow-up. |
| **Data Connectors** `/data-connectors` | Browse connector capabilities and status labels, inspect connector details, and distinguish the three displayed operational entries from planned enterprise roadmap items. Status labels should be validated against deployment configuration before being presented as live feeds. |
| **AI Assistant** `/ai-assistant` | Ask natural-language questions about supported plant energy, production, SEC, and anomaly data; inspect tool references/evidence and numerical claim-verification outcomes. |
| **Platform Story** `/platform-story` | Interactive architecture and workflow explainer for demos and stakeholder presentations. It is a walkthrough, not the live pipeline execution screen. |

Legacy paths such as `/anomalies`, `/findings`, and `/recommendations-actions` redirect into the unified Investigation & Actions Centre.

## 7. Internal calculations and how they work

All authoritative analytics are computed by backend services from stored records. The UI presents those API results and some explicitly labeled hypothetical views.

### Energy

- **Energy total (kWh):** sum of the stored `consumption_kwh` readings in the selected plant/date scope.
- **Cost (INR):** sum of stored per-reading `cost_inr`; this is the dataset-calculated cost, not a verified current utility bill.
- **CO2e (kg):** sum of stored per-reading `co2e_kg`; it is a dataset-derived estimate, not a direct emissions measurement.
- **Meter/area share (%):** scoped meter or area kWh divided by scoped total kWh, multiplied by 100.
- **Average power factor:** energy-weighted mean, `SUM(power_factor × consumption_kwh) / SUM(consumption_kwh)` when available. The arithmetic mean is also exposed separately.
- **Peak reading:** the largest individual meter/hour consumption reading within the selected scope. It is not a plant-wide coincident peak-demand or utility-billing-demand calculation.

Energy cost and emissions values are aggregated from supplied/stored fields. Validate the source tariff and emissions factor against the applicable contract and reporting standard before using them for official billing or ESG disclosure.

### Production

For the selected scope, production quantities and downtime minutes are summed. Rates are calculated as:

- **Target achievement (%)** = actual quantity / target quantity × 100
- **Good-output yield (%)** = good quantity / actual quantity × 100
- **Reject rate (%)** = rejected quantity / actual quantity × 100
- **Rework rate (%)** = reworked quantity / actual quantity × 100

When a required denominator is zero or missing, the rate is unavailable rather than divided by zero. Rework is kept distinct from rejects. Downtime reason totals represent recorded reason codes, not independently verified root causes. Target achievement is not OEE; planned schedules and calendars required for OEE are not represented in the current data.

### Specific Energy Consumption (SEC)

- **SMT process SEC** = matched `MTR-SMT` process-meter kWh / actual SMT board output, reported as kWh/board.
- **Final Assembly (FAL) process SEC** = matched `MTR-FAL` process-meter kWh / actual phone output, reported as kWh/phone.
- **Factory SEC** = total plant energy across meters / Final Assembly finished output, with energy and output aligned to matching plant-hour records.
- SEC per good unit is also available for process-level results when good output is positive.

The process join requires matching plant, exact timestamp, and the designated process meter. Facility utility meters (HVAC, compressor, chiller) are not arbitrarily assigned to production lines or products. SMT boards and FAL phones are different units and must not be added or directly averaged. Factory SEC is not the same measure as process SEC. Missing alignment or a zero denominator makes the affected SEC unavailable.

### Anomaly detection

1. **Historical statistical Z-score:** compare an evaluation reading with its meter/plant historical baseline, using `(reading − baseline mean) / sample standard deviation`. The default threshold is an absolute Z-score of 3; the standard lookback is 30 days, with minimum history and baseline qualification checks. Evaluation rows are excluded from the baseline. A zero-variance or insufficient/unqualified baseline is surfaced as such rather than treated as normal.
2. **Rolling baseline:** compare the current reading to a historical rolling window (default 24 elapsed hours) and the configured Z threshold. The current observation is excluded from its own baseline.
3. **Low power factor:** flag readings below the application monitoring threshold, default 0.90. This is an engineering monitoring threshold, not by itself proof of a statutory violation or utility penalty.
4. **Zero-production process energy:** identify a matched line interval with zero recorded output and positive consumption on the corresponding process meter. This is observed energy during a zero-output interval; it is not automatically avoidable waste or a quantified saving.

Z-score severity bands are deterministic: absolute Z at least 4 is CRITICAL, at least 3 is HIGH, at least 2.5 is MEDIUM, otherwise LOW. Signals from different detectors may refer to the same underlying interval, so detector counts should not be added as unique incidents without deduplication.

### Tariff what-if

The Energy Analytics page accepts a non-negative user-entered flat tariff and calculates:

- **Scenario cost** = returned reference kWh × entered INR/kWh
- **Cost difference** = scenario cost − dataset-calculated reference cost
- **Percentage difference** = cost difference / reference cost × 100, when reference cost is positive

This is a hypothetical scenario only; it does not update stored tariffs or recalculate historical data. It excludes time-of-use tariffs, demand charges, taxes, penalties, and fixed charges. A negative difference is not a claim of achieved savings.

### Baseline qualification and data confidence

Before using a historical series as a baseline, the qualification logic checks temporal separation, expected versus observed data coverage, missing-data gaps, reading quality when supplied, negative values, and flat-line/zero-variance behavior. It reports **QUALIFIED**, **INCONCLUSIVE**, or **NOT_QUALIFIED**, with reason codes. Thresholds are engineering defaults and need plant/operator approval; they are not universal industry or regulatory standards.

## 8. Architecture and operational boundaries

- **Frontend:** React 18, Vite, React Router, and Recharts.
- **Backend:** Python FastAPI REST API with SQLAlchemy and Alembic.
- **Persistence:** PostgreSQL for source facts and operational records; uploaded report batches and findings support lineage/audit use cases.
- **AI:** Domo text-generation API for tool selection and answer composition; deterministic backend services remain authoritative for figures.
- **Data inputs currently demonstrated:** hourly meter and production records, plus daily CSV/XLS/XLSX report ingestion. The current data model includes plant, meter, line, product, shift, energy, production, and operational lifecycle concepts.

Important deployment and scope notes:

- The backend README describes a single-process operational model; daily pipeline locking is in-process, so multi-worker deployment needs a distributed lock or database-backed coordination.
- The connector page labels Neon, MongoDB, and SharePoint as operational and lists other systems as roadmap. However, the connector catalog is UI-defined and the connector service keeps non-primary connector registrations and sync history in memory. Confirm real credentials, persistence, scheduled synchronization, and source-to-ingestion wiring before describing a connector as a production-live feed.
- The Platform Story animation contains **nine illustrative steps**, while the actual Daily Operations pipeline has **eight**. Its sample values and simulated artifacts are walkthrough content, not proof of current plant measurements, completed integrations, verified savings, or live pipeline output.
- Do not describe the application as predictive maintenance, autonomous control, verified savings measurement, OEE analytics, or a full ERP/MES integration unless those capabilities are separately implemented and validated.

## 9. Suggested demo sequence

1. Start on **Dashboard** to frame the plant-level question and high-level signals.
2. Open **Daily Operations** and walk through a report upload, validation result, ingestion provenance, and pipeline stage status.
3. Open **Energy Analytics** to explain meter/area consumption, power factor, cost/emissions caveats, and the clearly hypothetical tariff scenario.
4. Open **Production Analytics** and show how production, quality, shift/line, and logged downtime context help interpret energy.
5. Explain process versus factory SEC and show why the app keeps SMT boards, FAL phones, and facility utilities separate.
6. Run or open **Live Anomaly Surveillance**, then inspect the linked finding and source evidence in **Investigation & Actions Centre**.
7. Show a recommendation and corrective action lifecycle, emphasizing auditability and the fact that action completion is not the same as verified energy savings.
8. Ask the **AI Assistant** an evidence-based question and show its tool references and claim verification.
9. Finish with **Platform Story**, explicitly identifying its walkthrough/demo content and roadmap boundaries.

## 10. Closing statement for the review

> “Energy Intel connects factory energy and production records to make daily performance easier to understand and investigate. It validates incoming reports, preserves their lineage, calculates energy and production metrics with explicit scope rules, flags unusual telemetry with baseline-quality caveats, and provides a traceable path from finding to corrective action. Its AI assistant helps users ask questions, but deterministic services—not the language model—produce the authoritative numbers. The platform is an operational intelligence and workflow-support foundation; live integrations, quantified savings, and equipment root causes must be proven with validated plant data and deployment-specific evidence.”

### Source grounding in the repository

This report is based on the implemented UI routes/components, FastAPI APIs, analytical and pipeline services, agent/tool registry, and project README. Particularly relevant sources include:

- `ui/src/App.jsx` and `ui/src/components/Sidebar.jsx` — routes and navigation.
- `backend/app/services/daily_pipeline_service.py` — actual eight-stage pipeline.
- `backend/app/services/energy_analytics.py`, `production_analytics.py`, `energy_intensity.py`, and `anomaly_detection.py` — analytics calculations.
- `backend/app/services/agent/agent.py`, `tool_registry.py`, `prompts.py`, and `evidence_verifier.py` — assistant/tool/evidence flow.
- `backend/app/services/recommendation_service.py` and `connector_service.py` — operational lifecycle and connector implementation details.
- `ui/src/pages/PlatformStory.jsx` — illustrative walkthrough and simulated content.
