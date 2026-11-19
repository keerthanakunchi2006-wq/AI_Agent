# Supply Chain Disruption & Replanning System — Architecture

## 1. Overview

A production-style, multi-agent AI application that detects supply-chain
disruptions, estimates their impact, forecasts demand/shortages, evaluates
alternative suppliers, optimizes sourcing, generates replanned purchase orders,
routes consequential changes through human approval, and tracks recovery.

```
┌─────────────┐     HTTPS/JSON     ┌──────────────┐   Pydantic    ┌────────────────────┐
│  Web UI     │ ─────────────────▶ │  FastAPI     │ ────────────▶ │ LangGraph Agent    │
│  (Dashboard)│ ◀───────────────── │  (Uvicorn)   │ ◀──────────── │ Orchestrator       │
└─────────────┘                    └──────────────┘               └─────────┬──────────┘
        │                                  │                                 │
        │                                  │          ┌──────────────────────┴──────────┐
        │                                  │          ▼              ▼                ▼         ▼
        │                                  │   Monitoring   ImpactAnalysis   Forecasting  SupplierEval
        │                                  │     Agent        Agent           Agent        Agent
        │                                  │                                              │
        │                                  │          ▼              ▼                ▼
        │                                  │   Optimization   Approval        Tracking
        │                                  │     Agent          Agent           Agent
        │                                  │
        │                                  ▼
        │                          ┌────────────────────┐    ┌────────────┐
        │                          │  PostgreSQL         │    │  Redis     │
        │                          │  (records, models,   │    │  (cache,   │
        │                          │   LangGraph ckpts)   │    │   queues)  │
        │                          └────────────────────┘    └────────────┘
        │
        ▼
   Structlog logs · Prometheus metrics · Pytest
```

## 2. Technology mapping

| Concern              | Technology                                  |
|----------------------|---------------------------------------------|
| Backend / API        | Python 3.11, FastAPI, Uvicorn, Pydantic v2  |
| Agent orchestration  | LangGraph (StateGraph), checkpoint in PG     |
| Database             | PostgreSQL (SQLite fallback for local dev)  |
| ORM / migrations     | SQLAlchemy 2.x, Alembic                     |
| Caching / queues     | Redis (in-memory fallback for local dev)    |
| Data                 | Pandas, scikit-learn, OR-Tools              |
| Monitoring           | structlog, prometheus-client                |
| Testing              | pytest, httpx                                |
| Deployment           | Docker, docker-compose                      |

## 3. Multi-agent workflow (LangGraph)

```
        ┌──────────────┐
        │  monitoring  │──▶ delays[], supplier_perf
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ impact_      │──▶ affected_orders, affected_products, inventory_gap
        │ analysis     │
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ forecasting  │──▶ predicted_demand, shortage_predictions
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ supplier_    │──▶ alternative_suppliers[] (scored)
        │ evaluation  │
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ optimization │──▶ recovery_plan (min cost / min delay, OR-Tools)
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  approval    │──▶ approval_request (human-in-the-loop)
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  tracking    │──▶ decision_record, status
        └──────────────┘
```

State is a TypedDict shared across nodes and persisted via LangGraph
checkpoints so runs resume after interruption (e.g. awaiting human approval).

## 4. Data model

Core tables: `suppliers`, `products`, `inventory`, `purchase_orders`,
`purchase_order_items`, `deliveries`, `supplier_performance`, `customers`,
`customer_orders`, `transportation`, `disruptions`, `recovery_plans`,
`recovery_plan_items`, `approval_requests`, `decision_history`, `users`.

Full schema lives in `backend/app/models.py` and Alembic migrations.

## 5. Production qualities

- **Configurable, secrets-free**: all settings via env vars / `.env`.
- **Database portability**: `DATABASE_URL` defaults to SQLite for instant
  local runs; set a Postgres URL for production. LangGraph uses MemorySaver
  locally and PostgresSaver when a PG URL is configured.
- **Cache portability**: Redis optional; in-memory fallback for dev.
- **Error handling**: bounded retries per agent node; failed nodes mark state
  and continue rather than crashing the graph.
- **Observability**: structured logs (structlog) + Prometheus metrics
  (request latency, agent durations, delay count, approval throughput).
- **Auth**: JWT bearer with role-based access (analyst, approver, admin).
- **Human-in-the-loop**: optimization results that exceed a cost/delay
  threshold automatically route to the Approval Agent for sign-off.
- **Sandbox**: every supplier/PO action is simulated; no external system is
  contacted.
