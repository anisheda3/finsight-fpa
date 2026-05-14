"""Boots the FastAPI app in-process and verifies routes are registered.

Does NOT require Postgres/Redis/Temporal to be live — only fastapi must be installed.
"""
from __future__ import annotations

import importlib

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Force lifespan to run with degraded backends (no DB/Redis).
    app = importlib.import_module("app.main").app
    with TestClient(app) as c:
        yield c


def test_health_route_returns_payload(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    for key in ("env", "db", "temporal", "redis"):
        assert key in data


def test_correlation_id_middleware_echoes_header(client):
    r = client.get("/api/v1/health", headers={"x-correlation-id": "abc-123"})
    assert r.headers.get("x-correlation-id") == "abc-123"


def test_correlation_id_generated_when_missing(client):
    r = client.get("/api/v1/health")
    assert r.headers.get("x-correlation-id")  # auto-generated UUID


def test_required_routes_registered(client):
    paths = {r.path for r in client.app.routes}
    expected = {
        "/api/v1/health",
        "/api/v1/actuals/upload",
        "/api/v1/actuals/{company_id}",
        "/api/v1/forecasts/{company_id}",
        "/api/v1/forecasts/rerun",
        "/api/v1/variances/{company_id}",
        "/api/v1/insights/scenarios/run",
        "/api/v1/insights/scenarios/{company_id}",
        "/api/v1/insights/commentary/{company_id}/{period}",
        "/api/v1/hitl/respond",
        "/api/v1/hitl/{flag_id}/override",
        "/api/v1/hitl/pending",
        "/api/v1/webhooks/slack",
        "/ws/workflow/{workflow_id}",
    }
    missing = expected - paths
    assert not missing, f"missing routes: {sorted(missing)}"
