import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_fault():
    client.post("/chaos/reset")
    yield
    client.post("/chaos/reset")


def test_healthz():
    assert client.get("/healthz").json()["status"] == "ok"


def test_orders_ok():
    r = client.get("/api/v1/orders")
    assert r.status_code == 200 and len(r.json()["orders"]) == 3


def test_not_found():
    assert client.get("/api/v1/orders/999").status_code == 404


def test_metrics_have_version_label_and_golden_signals():
    client.get("/api/v1/orders")
    body = client.get("/metrics").text
    assert 'http_requests_total{method="GET",path="/api/v1/orders",status="200",version=' in body
    assert "http_request_duration_seconds_bucket" in body
    assert "http_requests_in_flight" in body


def test_fault_injection_produces_5xx_metrics():
    client.post("/chaos/fault", json={"error_rate": 1.0, "latency": 0})
    assert client.get("/api/v1/orders").status_code == 500
    assert 'status="500"' in client.get("/metrics").text


def test_reset_restores_service():
    client.post("/chaos/fault", json={"error_rate": 1.0, "latency": 0})
    client.post("/chaos/reset")
    assert client.get("/api/v1/orders").status_code == 200


def test_invalid_fault_rejected():
    assert client.post("/chaos/fault", json={"error_rate": 2}).status_code == 422
