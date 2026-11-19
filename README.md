# Supply Chain Disruption & Replanning System

A production-style, multi-agent AI application that detects supply-chain
disruptions, estimates their impact, forecasts demand and shortages, evaluates
alternative suppliers, optimises sourcing with OR-Tools, generates replanned
purchase orders, routes consequential changes through human approval, and
tracks recovery — all orchestrated by a LangGraph multi-agent workflow.

Built for **Assignment 04 – Advanced AI Agent Application**.

---

## 1. What it does

| Capability | How |
|---|---|
| Supplier delay detection | Monitoring Agent scans POs past expected delivery with no actual arrival |
| Affected order/product estimation | Impact Analysis Agent walks supplier → products → open POs → customer orders → inventory gap |
| Demand forecasting & shortage prediction | Forecasting Agent fits per-product LinearRegression (trend + seasonality) on customer-order history (scikit-learn) |
| Alternative supplier recommendation | Supplier Evaluation Agent scores candidates on cost, delay, reliability, quality |
| Transportation & sourcing optimisation | Optimisation Agent solves an LP with OR-Tools (GLOP) to minimise cost + delay penalty |
| Purchase order replanning | Optimised plan materialised as `recovery_plans` + `recovery_plan_items` |
| Delivery delay estimation | Per-line `delay_days` vs a 7-day baseline |
| What-if disruption simulation | `/simulations/what-if` runs the deterministic pipeline on a hypothetical disruption |
| Recovery plan comparison | Original (single-supplier) vs optimised (multi-supplier) on total cost and delay |
| Human approval | Plans above a cost/delay threshold create `approval_requests` for sign-off |
| Decision tracking | Every workflow step is appended to `decision_history` |

All supplier and purchase actions are **simulated/sandboxed** — no external
system is ever contacted.

---

## 2. Architecture

```
Web UI (dashboard) ──HTTP/JSON──▶ FastAPI ──Pydantic──▶ LangGraph Orchestrator
                                      │                        │
                                      ▼                        ▼
                              PostgreSQL / SQLite        Specialist Agents (7)
                                      │                        │
                                      ▼                        ▼
                                Redis / in-memory      Pandas · scikit-learn · OR-Tools
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design, data model and
the multi-agent workflow diagram.

**Agents (LangGraph StateGraph):**
`Monitoring → Impact Analysis → Forecasting → Supplier Evaluation →
Optimisation → Approval → Tracking`

State is a `TypedDict` persisted via LangGraph checkpoints (Postgres in
production, in-memory locally) so runs resume after interruption.

---

## 3. Tech stack

| Concern | Tech |
|---|---|
| Backend / API | Python 3.11, FastAPI, Uvicorn, Pydantic v2 |
| Agents | LangGraph (StateGraph), checkpoint in Postgres |
| DB / migrations | SQLAlchemy 2.x, Alembic, PostgreSQL (SQLite fallback) |
| Cache / queues | Redis (in-memory fallback) |
| Data / AI | Pandas, scikit-learn, OR-Tools |
| Observability | structlog, prometheus-client |
| Testing | pytest, httpx |
| Deployment | Docker, docker-compose |

---

## 4. Quick start (local, no Docker)

Prerequisites: Python 3.11+.

```powershell
# from the repo root
cd backend

# 1. create virtual env (recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. install dependencies
pip install -r requirements.txt

# 3. generate the dataset CSVs (>10,000 records) and seed the DB
python -m scripts.seed_db          # SQLite at backend/supply_chain.db

# 4. run the API (also serves the dashboard at http://localhost:8000/ui)
uvicorn app.main:app --reload --port 8000
```

Then open:
- **Dashboard**: http://localhost:8000/ui  (or http://localhost:8000/)
- **API docs (Swagger)**: http://localhost:8000/docs
- **Prometheus metrics**: http://localhost:8000/metrics

**Demo logins:** `admin/admin123`, `approver/approver123`, `analyst/analyst123`

The app auto-seeds on first start (SQLite by default). No PostgreSQL or Redis
required for local dev — both fall back to in-process stores automatically.

---

## 5. Quick start (Docker / production-style)

```powershell
# from repo root — brings up Postgres + Redis + backend
docker-compose up --build
```

This runs PostgreSQL, Redis and the backend with:
- `DATABASE_URL=postgresql+psycopg2://scdemo:scdemo@db:5432/supplychain`
- durable LangGraph checkpoints in Postgres
- Redis cache

Open http://localhost:8000/ui.

---

## 6. Running the dataset generator only

```powershell
cd backend
python -m scripts.generate_dataset        # writes CSVs to data/
python -m scripts.seed_db --gen-only       # CSVs only, no DB
python -m scripts.seed_db --force          # wipe + reseed
```

The generator produces ~45,000+ rows across tables; the combined
`supply_chain_dataset.csv` alone has >12,000 purchase-order line rows. See the
table breakdown printed at the end of generation.

---

## 7. Database migrations (Alembic)

```powershell
cd backend
alembic upgrade head      # apply schema
alembic revision --autogenerate -m "describe change"
```

The first migration (`0001_initial_schema`) creates all tables from the
SQLAlchemy models. For SQLite local dev, `app.database.init_db` is used instead.

---

## 8. Tests

```powershell
cd backend
pytest                    # full suite
pytest tests/test_services.py -v
pytest tests/test_agents.py -v
pytest tests/test_api.py -v
```

Tests use an in-memory SQLite DB seeded with a synthetic subset and override
auth, so they run without Postgres/Redis/JWT. See `tests/` for the cases.

---

## 9. Project structure

```
AI_Agent/
├── ARCHITECTURE.md
├── README.md
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app + middleware + lifespan
│   │   ├── config.py               # Pydantic settings (env-driven)
│   │   ├── database.py             # SQLAlchemy engine/session
│   │   ├── models.py               # ORM schema (all tables)
│   │   ├── schemas.py              # Pydantic request/response models
│   │   ├── auth.py / deps.py       # JWT auth + role checks
│   │   ├── cache.py                # Redis / in-memory cache
│   │   ├── seed.py                 # load dataset + demo users
│   │   ├── core/                   # structlog logging + Prometheus metrics
│   │   ├── routers/                # auth, dashboard, master, disruptions,
│   │   │                           #   simulations, recovery, approvals, forecasting
│   │   ├── services/               # monitoring, impact_analysis, forecasting,
│   │   │                           #   supplier_eval, optimization, approval, tracking
│   │   └── agents/                 # LangGraph state + 7 agents + orchestrator
│   ├── scripts/                    # generate_dataset.py, seed_db.py
│   ├── alembic/                    # migrations
│   ├── tests/                      # conftest, test_services, test_agents, test_api
│   ├── Dockerfile, pytest.ini, alembic.ini
│   └── requirements.txt
└── frontend/
    ├── index.html                  # single-page dashboard
    ├── css/styles.css
    └── js/                         # api.js, charts.js, app.js
```

---

## 10. API reference

Interactive docs at `/docs`. Key endpoints (all under `/api/v1`):

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | JWT login (OAuth2 password) |
| POST | `/auth/register` | Create user |
| GET | `/auth/me` | Current user |
| GET | `/dashboard/summary` | KPI summary |
| GET | `/dashboard/risk-alerts` | Live risk alerts |
| GET | `/dashboard/supplier-performance` | Supplier performance chart data |
| GET | `/dashboard/demand-forecast` | Demand forecast chart data |
| GET | `/master/suppliers` | List suppliers |
| GET | `/master/products` | List products |
| GET | `/master/inventory` | List inventory |
| GET | `/master/purchase-orders` | List purchase orders |
| GET | `/master/deliveries` | List deliveries |
| GET | `/forecasting/demand` | Demand forecast per product |
| GET | `/forecasting/shortages` | Products at risk of shortage |
| POST | `/disruptions/run` | **Run the full LangGraph workflow** |
| POST | `/simulations/what-if` | What-if disruption simulation |
| GET | `/recovery/plans` | List recovery plans |
| GET | `/recovery/plans/{id}/compare` | Original vs optimised comparison |
| GET | `/recovery/alternatives` | Ranked alternative suppliers |
| GET | `/approvals/pending` | Pending approvals |
| POST | `/approvals/{id}/decide` | Approve/reject (approver/admin) |
| GET | `/recovery/decisions` | Decision history |
| GET | `/metrics` | Prometheus metrics |

---

## 11. Acceptance scenarios

See [`SCENARIOS.md`](SCENARIOS.md) for the five required scenarios with
measurable results and the exact API/curl calls to reproduce them.

---

## 12. Production qualities

- **Secrets-free config** — everything via `.env` / env vars (`.env.example` template).
- **DB portability** — `DATABASE_URL` defaults to SQLite; set Postgres for production.
- **Cache portability** — Redis optional; in-memory fallback.
- **Error handling** — bounded retries per agent node; failures are recorded in state, never crash the graph.
- **Checkpoint recovery** — LangGraph checkpoints let runs resume after interruption (e.g. awaiting approval).
- **Observability** — structured JSON logs (structlog) + Prometheus metrics (`/metrics`).
- **Auth & RBAC** — JWT bearer with `admin`/`approver`/`analyst` roles; approvals restricted to approver/admin.
- **Human-in-the-loop** — recovery plans above `APPROVAL_COST_THRESHOLD` / `APPROVAL_DELAY_THRESHOLD_DAYS` require sign-off.
- **Sandbox** — every supplier/PO action is simulated.
