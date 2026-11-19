"""LangGraph orchestrator — wires the seven specialist agents into a
StateGraph with checkpoint persistence so runs survive interruption.

Checkpointing:
  - If ``CHECKPOINT_DB_URL`` points at Postgres we use ``PostgresSaver``.
  - Otherwise we use ``MemorySaver`` (durable only while the process lives).

Each agent node is wrapped so it opens its own DB session; the shared state
moves between nodes as a serialisable TypedDict, so no SQLAlchemy objects
leak across the graph.
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from ..config import settings
from ..database import db_session
from ..core.logging import get_logger
from .state import AgentState
from .monitoring_agent import monitoring_node
from .impact_analysis_agent import impact_analysis_node
from .forecasting_agent import forecasting_node
from .supplier_evaluation_agent import supplier_evaluation_node
from .optimization_agent import optimization_node
from .approval_agent import approval_node
from .tracking_agent import tracking_node

log = get_logger("orchestrator")


def _wrap(fn):
    """Wrap an (state, db) agent node as a LangGraph (state)->dict node."""
    def wrapped(state: dict) -> dict:
        with db_session() as db:
            return fn(dict(state), db)
    return wrapped


def _build_checkpointer():
    if settings.use_postgres_checkpoint:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
            # PostgresSaser needs its own psycopg connection
            import psycopg  # type: ignore
            conn = psycopg.connect(settings.CHECKPOINT_DB_URL, autocommit=False)
            saver = PostgresSaver(conn)
            saver.setup()
            log.info("orchestrator.checkpointer", backend="postgres")
            return saver
        except Exception as e:  # pragma: no cover
            log.warning("orchestrator.postgres_checkpoint_failed", error=str(e))
    log.info("orchestrator.checkpointer", backend="memory")
    return MemorySaver()


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("monitoring", _wrap(monitoring_node))
    g.add_node("impact_analysis", _wrap(impact_analysis_node))
    g.add_node("forecasting", _wrap(forecasting_node))
    g.add_node("supplier_evaluation", _wrap(supplier_evaluation_node))
    g.add_node("optimization", _wrap(optimization_node))
    g.add_node("approval", _wrap(approval_node))
    g.add_node("tracking", _wrap(tracking_node))

    g.set_entry_point("monitoring")
    g.add_edge("monitoring", "impact_analysis")
    g.add_edge("impact_analysis", "forecasting")
    g.add_edge("forecasting", "supplier_evaluation")
    g.add_edge("supplier_evaluation", "optimization")
    g.add_edge("optimization", "approval")
    g.add_edge("approval", "tracking")
    g.add_edge("tracking", END)

    return g.compile(checkpointer=_build_checkpointer())


# compiled graph singleton (built lazily so import never opens connections)
_app_graph = None


def get_graph():
    global _app_graph
    if _app_graph is None:
        _app_graph = build_graph()
    return _app_graph


def run_workflow(initial_state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Execute the full disruption-recovery workflow.

    Returns ``(thread_id, final_state)``. ``thread_id`` is the LangGraph
    checkpoint thread so the run can be inspected/resumed later.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    initial_state.setdefault("errors", [])
    initial_state.setdefault("run_optimization", True)
    initial_state.setdefault("request_approval", True)
    final_state = graph.invoke(initial_state, config=config)
    final_state["thread_id"] = thread_id
    return thread_id, final_state
