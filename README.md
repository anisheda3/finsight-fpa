# FinSight FP&A AI

Autonomous financial planning & analysis platform for monthly close.
Built for **Fyntwin Assignment #2** — 8 Agno agents · 2 teams · 2 workflows · Temporal sagas · FastAPI · React UI.

---

## Architecture

```
Actuals CSV ──► FastAPI /actuals/upload ──► Temporal MonthEndAnalysisSaga
                                              │
                                              ▼
                                        AnalysisTeam
                                  (Forecast ‖ Variance ‖ Anomaly)
                                              │
                                  HITL flags? ──► Slack (interactive)
                                              │      │
                                              │   FastAPI /webhooks/slack
                                              │      │  (signal Temporal)
                                              ▼      ▼
                                          InsightsTeam
                                  (Document → Scenarios → Commentary
                                   → Notification → Audit)
                                              │
                                              ▼
                                       Dashboard (WebSocket)
```

## Environment Setup

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:

```env
# LLM Configuration (choose one provider)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key-here
LLM_MODEL=gemini-1.5-flash

# Or for OpenAI fallback
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key-here
LLM_MODEL=gpt-4o-mini

# Database
POSTGRES_URL=postgresql://postgres:password@localhost:5432/finsight_fpa

# Redis
REDIS_URL=redis://localhost:6379/0

# Temporal
TEMPORAL_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=finsight-fpa

# Slack (optional)
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_HITL_CHANNEL=#fpa-hitl
```

## Quick start

```bash
# 1) Boot infra
docker compose up -d postgres redis temporal temporal-ui

# 2) Install Python deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3) Apply schema + seed
psql "$POSTGRES_URL" -f db/migrations.sql
POSTGRES_URL=postgresql://postgres:password@localhost:5432/finsight_fpa \
    python scripts/seed_data.py

# 4) Run the Temporal worker (one terminal)
python temporal/worker.py

# 5) Run the API (another terminal)
uvicorn app.main:app --reload --port 8000

# 6) Run the frontend
cd frontend && npm install && npm run dev
```

Health check:
```bash
curl http://localhost:8000/api/v1/health
```

Upload Q3 actuals:
```bash
curl -F company_id=<UUID> -F file=@sample_data/FTPL-001_Q3_2024_Actuals.csv \
     http://localhost:8000/api/v1/actuals/upload
```

## Tests

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

## Endpoints (matches spec)

| Method | Path |
|---|---|
| POST | `/api/v1/actuals/upload` |
| GET | `/api/v1/actuals/{company_id}` |
| GET | `/api/v1/forecasts/{company_id}` |
| POST | `/api/v1/forecasts/rerun` |
| GET | `/api/v1/variances/{company_id}` |
| POST | `/api/v1/insights/scenarios/run` |
| GET | `/api/v1/insights/commentary/{company_id}/{period}` |
| GET | `/api/v1/insights/scenarios/{company_id}` |
| POST | `/api/v1/hitl/respond` |
| POST | `/api/v1/hitl/{flag_id}/override` |
| POST | `/api/v1/webhooks/slack` |
| GET | `/api/v1/health` |
| WS | `/ws/workflow/{workflow_id}` |

## Spec compliance highlights

- **Forecasting** (`agents/tools/forecasting_tools.py`): real Prophet → SARIMA → linear chain with **holdout MAPE** and **80% / 95% CIs**. The LLM picks the model and writes the explanation; the math is in the tool.
- **Variance**: materiality from `kpi_definitions` (no hardcoded numbers), favorable/unfavorable per metric direction, signed EBITDA waterfall ranked by absolute impact.
- **Idempotency + lineage**: `UNIQUE` constraints + `source_file_hash` on actuals; FK lineage on variance/anomaly; `run_id` on forecasts.
- **HITL**: Slack interactive buttons → `POST /webhooks/slack` → `workflow.signal("hitl_decision", ...)` → workflow `wait_condition` resumes.
- **Guardrails**: `DataSanityGuardrail`, `ForecastReasonablenessGuardrail`, `CommentaryGroundingGuardrail` (the corrected one — reads `_analysis_context`/`analysis_data`, not a fictional `allowed_figures`).
- **Evals**: `ForecastAccuracyEval` (post-hoc MAPE) and `CommentaryGroundingEval` (regex coverage + optional OpenAI LLM-as-judge).
- **Memory**: `MemoryManager` backed by Postgres `agent_memory` table; ForecastingAgent calls `search_forecast_memory_tool` before each run.
- **Hooks**: `session_start_hook` and `tool_post_exec_hook` push to `agent_activity:{agent_name}:{session_id}` Redis Stream.
