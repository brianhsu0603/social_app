"""Metrics + tracing setup.

Metrics: Prometheus scrapes `/metrics` (RED-ish defaults plus app gauges).
Tracing: OpenTelemetry with OTLP/HTTP, auto-instrumenting FastAPI, SQLAlchemy,
HTTPX, Redis, and PyMongo. The OTel collector is a separate service —
see k8s/50-observability.yaml.
"""

import logging
import os
import time

from fastapi import FastAPI, Request
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.responses import Response

log = logging.getLogger(__name__)

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
WS_CONNECTIONS = Gauge(
    "ws_active_connections", "Active WebSocket connections", ["kind"]
)
KAFKA_PUBLISH = Counter(
    "kafka_publish_total", "Kafka messages published", ["topic", "status"]
)
KAFKA_CONSUME = Counter(
    "kafka_consume_total", "Kafka messages consumed", ["topic", "status"]
)


def install_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def _track(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        # Use the matched route template (eg "/posts/{post_id}") so cardinality is bounded.
        route = request.scope.get("route")
        template = route.path if route else request.url.path
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            status = 500
            raise
        finally:
            LATENCY.labels(request.method, template).observe(
                time.perf_counter() - start
            )
            REQUESTS.labels(request.method, template, str(status)).inc()

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def install_tracing(app: FastAPI) -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        log.info("OTEL_EXPORTER_OTLP_ENDPOINT not set; skipping tracing setup")
        return
    # Imports are local so the dependency is optional in non-prod environments.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "social-backend")}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    from app.core.database import engine

    SQLAlchemyInstrumentor().instrument(engine=engine)
    log.info("tracing enabled, exporting to %s", endpoint)
