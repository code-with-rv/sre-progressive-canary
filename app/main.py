"""Orders microservice: Golden Signal metrics + fault injection for canary demos."""
import asyncio
import os
import random
import time

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

VERSION = os.environ.get("APP_VERSION", "dev")
EXCLUDED_PATHS = {"/metrics", "/healthz"}  # keep probes/scrapes out of SLIs

# Metric names and labels match k8s/analysis-template.yaml
REQUESTS = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status", "version"]
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path", "version"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0),
)
IN_FLIGHT = Gauge("http_requests_in_flight", "In-flight HTTP requests (saturation)", ["version"])

fault = {
    "error_rate": float(os.environ.get("FAULT_ERROR_RATE", "0")),
    "latency": float(os.environ.get("FAULT_LATENCY_SECONDS", "0")),
}

ORDERS = [
    {"id": 1, "item": "keyboard", "qty": 1},
    {"id": 2, "item": "monitor", "qty": 2},
    {"id": 3, "item": "usb-c cable", "qty": 5},
]

app = FastAPI(title="orders-service", version=VERSION)


class FaultConfig(BaseModel):
    error_rate: float = Field(0.0, ge=0.0, le=1.0)
    latency: float = Field(0.0, ge=0.0, le=10.0)


@app.middleware("http")
async def observe(request: Request, call_next):
    if request.url.path in EXCLUDED_PATHS:
        return await call_next(request)
    IN_FLIGHT.labels(VERSION).inc()
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - start
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")  # route template avoids label explosion
        IN_FLIGHT.labels(VERSION).dec()
        REQUESTS.labels(request.method, path, str(status), VERSION).inc()
        LATENCY.labels(request.method, path, VERSION).observe(elapsed)


async def apply_faults() -> None:
    if fault["latency"] > 0:
        await asyncio.sleep(fault["latency"])
    if random.random() < fault["error_rate"]:
        raise HTTPException(status_code=500, detail="injected fault")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": VERSION}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/orders")
async def list_orders():
    await apply_faults()
    return {"version": VERSION, "orders": ORDERS}


@app.get("/api/v1/orders/{order_id}")
async def get_order(order_id: int):
    await apply_faults()
    for order in ORDERS:
        if order["id"] == order_id:
            return order
    raise HTTPException(status_code=404, detail="order not found")


@app.get("/chaos")
def get_fault():
    return fault


@app.post("/chaos/fault")
def set_fault(cfg: FaultConfig):
    fault.update(error_rate=cfg.error_rate, latency=cfg.latency)
    return fault


@app.post("/chaos/reset")
def reset_fault():
    fault.update(error_rate=0.0, latency=0.0)
    return fault
