# Industrial Energy Intelligence Platform

An enterprise industrial energy intelligence and operations platform designed to monitor energy consumption, track production correlation, detect anomalies, conduct multi-stage daily operational handoffs, manage investigations, and orchestrate corrective actions with an AI-powered assistant.

---

## 1. Platform Architecture

The platform follows a three-tier architecture:

```
[ Industrial Data Sources ]
  - Hourly Smart Energy Meters (10 streams across SMT, FAL, HVAC, Compressors, Chillers)
  - Hourly Production Lines (Line 1 to 4 output, rejects, downtime)
  - Daily Manual / Automated Excel & CSV Reports
        │
        ▼
[ FastAPI Backend (Python 3.11+) ]
  - REST Endpoints: Daily Operations, Analytics, Anomalies, Findings, Recommendations, Connectors, AI Assistant
  - Persistence Layer: PostgreSQL with SQLAlchemy ORM & Alembic migrations
  - Analytical Services: Statistical Z-Score, 14-Day Rolling Baselines, Low Power Factor (<0.90), Standby Energy
  - AI Assistant: Domo LLM integration with function calling, bounded retries (3 total attempts), and deterministic greeting routing
        │
        ▼
[ React 18 + Vite Modern Frontend ]
  - Responsive Dashboard with real-time KPI metrics and intensity tracking
  - Unified 8-Stage Daily Operations Pipeline
  - Investigation & Actions Centre (unified Anomaly Surveillance, Findings Centre, and Actions Tracker)
  - Interactive Platform Story & Architecture walkthrough
```

---

## 2. Platform Core Views

The application navigation consists of 8 primary views:

| # | Route | Title | Purpose |
|---|---|---|---|
| 1 | `/` | **Dashboard** | Executive overview of plant energy consumption, production output, Specific Energy Consumption (SEC), and live alert status. |
| 2 | `/daily-operations` | **Daily Operations** | End-to-end 8-stage operational pipeline: upload, validation, ingestion, deterministic reconciliation, analytics, intelligence report, anomaly detection, and investigation handoff. |
| 3 | `/energy-analytics` | **Energy Analytics** | Granular breakdown of power consumption, peak load, area distributions, power factor performance, and tariff what-if scenarios. |
| 4 | `/production-analytics` | **Production Analytics** | Line-by-line throughput analysis, scrap/reject monitoring, stoppage tracking, and SEC intensity correlation. |
| 5 | `/investigation-actions` | **Investigation & Actions Centre** | Unified workspace bringing together Anomaly Surveillance, Evidence Verification, Operational Findings, Recommendations, and Corrective Action lifecycle tracking. Legacy routes (`/anomalies`, `/findings`, `/recommendations-actions`) automatically redirect here preserving URL search parameters. |
| 6 | `/data-connectors` | **Data Connectors** | Telemetry ingestion status, connection health, ERP/SCADA synchronization logs, and source stream registration. |
| 7 | `/ai-assistant` | **AI Assistant** | Natural language industrial energy co-pilot with deterministic greeting handling, tool execution, and numeric claim evidence verification. |
| 8 | `/platform-story` | **Platform Story & Architecture** | Interactive presentation demonstrating system architecture, data provenance, analytical algorithms, and governance. |

---

## 3. Technology Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, Alembic, Pydantic, HTTPX.
- **Database:** PostgreSQL (local or cloud-hosted Neon PostgreSQL).
- **Frontend:** React 18, Vite, React Router v6, Recharts, Lucide Icons, CSS Modules.
- **AI Integration:** Domo AI Service API (`domo.domo_ai.domogpt-large-v2.2:anthropic`).

---

## 4. Setup and Installation

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL 14+

### Environment Configuration
Copy `.env.example` to `backend/.env` and update credentials:
```bash
cp .env.example backend/.env
```
Key configuration parameters:
- `DATABASE_URL`: PostgreSQL connection string (e.g. `postgresql://user:password@localhost:5432/energy_db`).
- `DOMO_BASE_URL`: Base URL for Domo AI service gateway.
- `DOMO_DEVELOPER_TOKEN`: API bearer token for AI services.
- `DOMO_MAX_RETRIES`: Maximum total attempts (default `3` = 1 initial + up to 2 retries).
- `DOMO_TIMEOUT_SECONDS`: Request timeout in seconds (default `30.0`).

### Backend Setup
```bash
cd backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Setup
```bash
cd ui
npm install
npm run dev
```
The frontend starts at `http://localhost:5173` and proxies API requests to `http://localhost:8000`.

### Building Frontend for Production
```bash
cd ui
npm run build
```

---

## 5. Architectural & Deployment Constraints

1. **Execution Model:**
   - The FastAPI backend is configured for single-process ASGI operation (`uvicorn`).
   - Concurrency protection for daily pipeline states uses in-process threading locks (`threading.Lock`). Multi-worker deployments (e.g. `--workers 4`) require an external distributed lock or direct row-level PostgreSQL state persistence.
2. **Time Boundary Semantics:**
   - All evaluation queries use half-open intervals: `timestamp >= eval_start AND timestamp < eval_end` ($[00:00, 24:00)$).
   - This guarantees that exactly 24 hourly readings are evaluated for a single reporting date without double-counting the next day's 00:00:00 midnight record.
3. **AI Transport & Retry Semantics:**
   - Network timeouts and transient 5xx/429 errors follow bounded exponential backoff (`0.5s`, `1.0s`) capped strictly at 3 total attempts (maximum cumulative delay of 1.5s).
   - Non-retryable errors (HTTP 401, 403, 400, 422) fail immediately on the initial attempt.
   - Pure conversational greetings are handled deterministically without incurring LLM latency or token usage.

