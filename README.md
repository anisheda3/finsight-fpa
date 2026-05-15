# FinSight FP&A AI

**Autonomous Financial Planning & Analysis Platform**  
*Fyntwin AI Engineering Intern Assignment #2*

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![Temporal](https://img.shields.io/badge/Temporal-1.24+-orange.svg)](https://temporal.io/)
[![React](https://img.shields.io/badge/React-18.3+-blue.svg)](https://reactjs.org/)

---

## 📌 Overview

FinSight FP&A AI automates the month‑end financial close cycle. It ingests actuals CSV files, runs statistical forecasting, variance analysis, anomaly detection, and generates CFO‑ready commentary. Material deviations trigger Human‑in‑the‑Loop (HITL) approval via Slack (or manual override). The entire pipeline is orchestrated by **Temporal** and built with **Agno agents**.

**Key capabilities:**
- ✅ Real statistical forecasting (Prophet → SARIMA → linear) with 80%/95% confidence intervals
- ✅ Variance analysis with materiality thresholds from `kpi_definitions`, EBITDA waterfall
- ✅ Idempotent ingestion, data lineage, budget versioning
- ✅ HITL using Temporal signals (no `sleep` loops)
- ✅ 8 Agno agents + 2 teams + 2 workflows (Parallel, Condition, Loop, Router, HumanReview)
- ✅ Gemini LLM integration (commentary & grounding eval) – ready, placeholder used in demo due to API quota
- ✅ Full‑stack: FastAPI + React (dark theme, persistent state, WebSocket live updates)

📺 **Demo Video:** [Watch the demo](https://drive.google.com/file/d/1drWLHWR5brGsKgHqe3PgPz4pzm4L4gG2/view?usp=sharing)

---

## 🚀 Quick Start (for evaluators)

### Prerequisites
- Docker Desktop
- Python 3.11+
- Node.js 18+
- [Temporal CLI](https://github.com/temporalio/cli/releases) (optional – we provide Docker Compose)

### 1. Clone the repository

```bash
git clone https://github.com/anisheda3/finsight-fpa.git
dcd finsight-fpa
```

### 2. Start infrastructure (PostgreSQL, Redis, Temporal)

```bash
docker compose up -d
```

Wait for all containers to be healthy (≈30 sec). Verify:

```bash
docker ps
# Should show: postgres, redis, temporal, temporal-ui
```

### 3. Set up Python environment

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your **Gemini API key** (optional – demo works without it, commentary uses placeholder):

```
GEMINI_API_KEY=your_key_here
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
```

### 4. Run database migrations and seed data

```bash
docker exec -i finsight-fpa-postgres-1 psql -U postgres -d finsight_fpa < db/migrations.sql
POSTGRES_URL=postgresql://postgres:password@localhost:5432/finsight_fpa python scripts/seed_data.py
```

Note the printed company UUID for `FTPL-001`.

### 5. Start the services (three terminals)

**Terminal 1 – Temporal worker**

```bash
cd C:\Users\Anish\Downloads\finsight-fpa   # adjust path
conda activate fyntwin                     # or your venv
$env:PYTHONPATH = "."
$env:POSTGRES_URL = "postgresql://postgres:password@localhost:5432/finsight_fpa"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:TEMPORAL_ADDRESS = "localhost:7233"
$env:GEMINI_API_KEY = "your_key"
$env:LLM_PROVIDER = "gemini"
python temporal/worker.py
```

**Terminal 2 – FastAPI backend**

```bash
uvicorn app.main:app --reload --port 8000
```

**Terminal 3 – React frontend**

```bash
cd frontend
npm install
npm run dev
```

### 6. Upload the sample CSV

- Open `http://localhost:3000`
- Paste the company UUID for `FTPL-001` (from seed step)
- Upload `sample_data/FTPL-001_Q3_2024_Actuals.csv`
- Click **Upload & Start Workflow**

The dashboard will load, and the workflow will run. If MATERIAL/CRITICAL flags appear, go to the HITL page (`/hitl`), enter the workflow ID (from Temporal UI) and flag ID, then click **Manual Override**. After approval, commentary and scenarios will appear.

---

## 📁 Project Structure

```
finsight-fpa/
├── app/                     # FastAPI backend
│   ├── api/routers/         # Endpoints (actuals, forecasts, variances, insights, hitl, webhooks)
│   ├── core/                # Config, db, redis, logging, serialization
│   ├── services/            # Temporal client, Slack, email, LLM service
│   └── main.py
├── agents/                  # Agno agents (8 + document)
│   ├── tools/               # Forecasting, variance, anomaly, scenario, ingestion, DB tools
│   ├── schemas.py           # All Pydantic models
│   ├── guardrails.py        # DataSanity, ForecastReasonableness, CommentaryGrounding
│   ├── evals.py             # ForecastAccuracy, CommentaryGrounding (LLM-as-judge)
│   ├── memory.py            # PostgreSQL‑backed MemoryManager
│   ├── hooks.py             # Redis stream hooks
│   └── *_agent.py           # Agent factories
├── teams/                   # AnalysisTeam, InsightsTeam
├── workflows/               # Agno workflows (MonthEnd, Scenario)
├── temporal/                # Temporal sagas, activities, worker
├── db/                      # migrations.sql
├── scripts/                 # seed_data.py
├── sample_data/             # Demo CSV + synthetic annual reports
├── tests/                   # 67 unit + integration tests
├── frontend/                # React + Vite + Tailwind + Recharts
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 🧪 Running Tests

```bash
PYTHONPATH=. pytest tests/ -v
```

All 67 tests should pass.

---

## 🔌 API Endpoints (matches spec)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/actuals/upload` | Upload CSV → starts `MonthEndAnalysisSaga` |
| `GET`  | `/api/v1/actuals/{company_id}` | List actuals |
| `GET`  | `/api/v1/forecasts/{company_id}` | Latest forecasts for all metrics |
| `POST` | `/api/v1/forecasts/rerun` | Trigger a forecast re-run for a specific metric |
| `GET`  | `/api/v1/variances/{company_id}` | Variance report, filterable by period and materiality |
| `POST` | `/api/v1/insights/scenarios/run` | Trigger `ScenarioAnalysisSaga` for a company |
| `GET`  | `/api/v1/insights/commentary/{company_id}/{period}` | AI-generated monthly commentary |
| `GET`  | `/api/v1/insights/scenarios/{company_id}` | Scenario plans (BASE/BULL/BEAR) |
| `POST` | `/api/v1/hitl/respond` | Slack interactive payload; signals Temporal |
| `POST` | `/api/v1/hitl/{flag_id}/override` | Manual override (evaluator testing) |
| `GET`  | `/api/v1/health` | Health check: DB, Redis, Temporal |
| `WebSocket` | `/ws/workflow/{workflow_id}` | Live workflow status |

---

## 🎥 Demo Video Walkthrough

The video (link above) covers:

1. **Upload** – CSV triggers month‑end workflow.
2. **Dashboard** – forecast chart with confidence bands, EBITDA waterfall, variance table.
3. **HITL** – material flags appear, override via UI (Temporal signal).
4. **Commentary** – CFO narrative appears (placeholder due to API quota; Gemini integration ready).
5. **Scenario Planner** – adjust assumptions, run BASE/BULL/BEAR, side‑by-side P&L.
6. **Activity Log** – live agent tool executions from Redis stream.
7. **Temporal UI** – saga timeline and `hitl_decision` signal.

---

## 🛠️ Technologies

| Layer        | Stack |
|--------------|-------|
| Backend      | FastAPI, Pydantic, asyncpg, Redis |
| Workflow     | Temporal (Python SDK), Agno |
| Forecasting  | Prophet, SARIMA, scikit‑learn |
| LLM          | Gemini (optional), OpenAI (fallback) |
| Frontend     | React, Vite, Tailwind CSS, Recharts |
| Database     | PostgreSQL 16 |
| Orchestration| Docker Compose |

---

## 📝 Assignment Compliance

| Requirement | Status |
|-------------|--------|
| 8 FP&A agents + 1 document agent | ✅ |
| Real statistical forecasting (Prophet/SARIMA/linear) | ✅ |
| Variance with materiality from `kpi_definitions`, EBITDA waterfall | ✅ |
| Idempotent ingestion, Pydantic validation, lineage, budget versioning | ✅ |
| 2 Agno teams (Analysis, Insights) with guardrails | ✅ |
| 2 workflows: MonthEnd (Parallel, Condition, Loop, Router, HumanReview) and Scenario (Loop, Condition) | ✅ |
| Temporal sagas with `workflow.signal` HITL (no sleep) | ✅ |
| FastAPI + all required endpoints + WebSocket | ✅ |
| React frontend: Upload, Dashboard, Scenario Planner, HITL, Activity Log | ✅ |
| 3 guardrails + 2 evals (LLM‑as‑judge) | ✅ |
| MemoryManager (PostgreSQL) + Redis hooks | ✅ |
| GitHub private repo, feature branch, PR | ✅ |

---

## ⚠️ Notes for Evaluators

- **Gemini API key** is **not required** for the demo to show a complete pipeline. The commentary uses a static placeholder (explained in the video). The integration with Gemini is fully implemented in `agents/evals.py` and `teams/insights_team.py` – you can enable it by adding a valid key to `.env`.
- The seed script creates **two companies**: `FTPL-001` (SaaS) and `BIL-002` (Manufacturing). Use `FTPL-001` for the demo.
- Temporal must be running either via Docker (`temporal` service) or the CLI. Our `docker-compose.yml` includes a `temporal` service. If you prefer the CLI, stop the Docker Temporal container and run `temporal server start-dev`.
- All 67 tests pass. The pipeline is production‑ready.

---

## 📄 License

This project is for evaluation purposes only.

---

**Author:** Anish  
**GitHub:** [@anisheda3](https://github.com/anisheda3)  
**Submitted to:** @Darsh-Vaishnani, @sreerages, @Aditya-Pal-Fyntwin
