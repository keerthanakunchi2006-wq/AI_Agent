"""Prometheus metrics.

Exposes counters and histograms that the /metrics endpoint scrapes. We keep
the registry explicit so tests can reset it.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

REGISTRY = CollectorRegistry()

REQUESTS = Counter(
    "sc_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
    registry=REGISTRY,
)

REQUEST_LATENCY = Histogram(
    "sc_api_request_latency_seconds",
    "API request latency in seconds",
    ["endpoint"],
    registry=REGISTRY,
)

AGENT_DURATION = Histogram(
    "sc_agent_duration_seconds",
    "Time spent inside an agent node",
    ["agent"],
    registry=REGISTRY,
)

AGENT_RUNS = Counter(
    "sc_agent_runs_total",
    "Total agent node executions",
    ["agent", "status"],
    registry=REGISTRY,
)

DELAYS_DETECTED = Gauge(
    "sc_delays_detected",
    "Currently detected supplier delays",
    registry=REGISTRY,
)

APPROVALS = Counter(
    "sc_approvals_total",
    "Approval requests by outcome",
    ["outcome"],
    registry=REGISTRY,
)
