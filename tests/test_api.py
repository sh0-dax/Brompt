"""Tests for the REST API layer (fastapi + httpx)."""

import pytest
from httpx import ASGITransport, AsyncClient

from brompt.api.routes import app
from brompt.core import BromptEngine
from brompt.feedback import FeedbackLoop


@pytest.fixture(autouse=True)
def _init_app_state():
    engine = BromptEngine(config_path="agent.brompt.yaml")
    app.state.engine = engine
    app.state.feedback = FeedbackLoop(
        storage_path=":memory:",
        audit_log=engine.audit,
    )


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_generate_prompt_dry_run(client):
    r = await client.post("/api/v1/prompts/generate", json={
        "template_id": "test",
        "user_input": "Hello world",
    })
    # dry-run mode succeeds without a provider
    assert r.status_code == 200
    data = r.json()
    assert data["template_id"] == "test"
    assert "is_secure" in data


@pytest.mark.asyncio
async def test_generate_prompt_blank_input_rejected(client):
    r = await client.post("/api/v1/prompts/generate", json={
        "template_id": "test",
        "user_input": "",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_record_feedback(client):
    r = await client.post("/api/v1/feedback/record", json={
        "template_id": "test",
        "outcome": "success",
        "latency_ms": 1500.0,
        "tokens_used": 200,
        "user_feedback": 5,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "recorded"


@pytest.mark.asyncio
async def test_record_feedback_invalid_outcome(client):
    r = await client.post("/api/v1/feedback/record", json={
        "template_id": "test",
        "outcome": "bogus",
        "latency_ms": 100,
        "tokens_used": 10,
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_performance_report(client):
    await client.post("/api/v1/feedback/record", json={
        "template_id": "perf_test", "outcome": "success",
        "latency_ms": 100, "tokens_used": 10,
    })
    r = await client.get("/api/v1/reports/performance")
    assert r.status_code == 200
    assert "summary" in r.json()


@pytest.mark.asyncio
async def test_templates_summary(client):
    r = await client.get("/api/v1/reports/templates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_template_health_not_found(client):
    r = await client.get("/api/v1/reports/templates/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_improvement_suggestions(client):
    r = await client.get("/api/v1/reports/suggestions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_best_template_no_data(client):
    r = await client.get("/api/v1/reports/best-template")
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
async def test_request_id_header(client):
    r = await client.get("/health")
    assert "X-Request-ID" in r.headers
    assert "X-Process-Time" in r.headers


@pytest.mark.asyncio
async def test_global_error_handler(client):
    r = await client.get("/api/v1/reports/templates/{}".format("a" * 999))
    assert r.status_code in (404, 500)
