"""FastAPI application factory + startup wiring.

Pipeline: Web UI -> FastAPI -> Pydantic validation -> LangGraph orchestrator ->
specialist agents -> PostgreSQL/SQLite + Redis/in-memory.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import settings
from .core.logging import configure_logging, get_logger
from .core.metrics import REQUESTS, REQUEST_LATENCY, REGISTRY
from .database import init_db
from .routers import (
    auth, dashboard, suppliers, disruptions, simulations,
    recovery, approvals, forecasting,
)

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    if settings.SEED_DEMO_DATA:
        try:
            from .seed import seed_database, is_seeded
            if not is_seeded():
                log.info("app.seeding_demo_data")
                seed_database()
            else:
                log.info("app.already_seeded")
        except Exception as e:  # pragma: no cover
            log.error("app.seed_failed", error=str(e))
    log.info("app.started", env=settings.APP_ENV, db=settings.DATABASE_URL,
             cache="redis" if settings.REDIS_URL else "memory")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Supply Chain Disruption & Replanning System — multi-agent AI application.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- middleware: request metrics + structured access log -------------------

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    endpoint = request.url.path
    REQUESTS.labels(method=request.method, endpoint=endpoint,
                    status=str(response.status_code)).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(elapsed)
    return response


# ---- routes ---------------------------------------------------------------

API = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=API)
app.include_router(dashboard.router, prefix=API)
app.include_router(suppliers.router, prefix=API)
app.include_router(disruptions.router, prefix=API)
app.include_router(simulations.router, prefix=API)
app.include_router(recovery.router, prefix=API)
app.include_router(approvals.router, prefix=API)
app.include_router(forecasting.router, prefix=API)


@app.get("/health", tags=["system"], summary="Liveness probe")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": "1.0.0"}


@app.get("/metrics", tags=["system"], summary="Prometheus metrics")
def metrics():
    return JSONResponse(
        content=generate_latest(REGISTRY).decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    # serve the dashboard if the frontend bundle is present, else a landing page
    frontend = Path(__file__).resolve().parent.parent.parent / "frontend" / "index.html"
    if frontend.exists():
        return HTMLResponse(frontend.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>Supply Chain Disruption &amp; Replanning System</h1>"
        f"<p>API docs: <a href='{API}/..{settings.API_V1_PREFIX}'>docs</a></p>"
        f"<p>OpenAPI at <a href='/docs'>/docs</a></p>"
    )


# Serve the frontend static files (dashboard) if present
_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_frontend_dir), html=True), name="ui")
