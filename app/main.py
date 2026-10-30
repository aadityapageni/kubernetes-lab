import os
import time
import random
from fastapi import FastAPI, Request
from fastapi.responses import Response
import requests
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

ROLE = os.getenv("ROLE", "frontend")
if ROLE not in {"frontend", "checkout", "inventory", "payment"}:
    raise ValueError(f"Unsupported ROLE: {ROLE}")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
resource = Resource.create({
    "service.name": ROLE,
    "service.namespace": os.getenv("OTEL_SERVICE_NAMESPACE", "otel-shop"),
    "deployment.environment.name": os.getenv("DEPLOYMENT_ENVIRONMENT", "local"),
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

app = FastAPI(title=f"OTel Shop - {ROLE}")
FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()
REQUESTS = Counter("shop_http_requests_total", "HTTP requests", ["service", "method", "path", "status"])
LATENCY = Histogram("shop_http_request_duration_seconds", "HTTP request duration", ["service", "method", "path"])

@app.middleware("http")
async def record_metrics(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    started = time.monotonic()
    response = await call_next(request)
    path = request.scope.get("route")
    route = path.path if path else "unmatched"
    REQUESTS.labels(ROLE, request.method, route, str(response.status_code)).inc()
    LATENCY.labels(ROLE, request.method, route).observe(time.monotonic() - started)
    return response

@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

def call_service(name: str, path: str = "/", params=None):
    url = os.getenv(f"{name.upper()}_URL", f"http://{name}:8080") + path
    response = requests.get(url, params=params, timeout=8)
    response.raise_for_status()
    return response.json()

@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": ROLE}

@app.get("/readyz")
def readyz():
    return {"status": "ready", "service": ROLE}

@app.get("/platform")
def platform():
    return {
        "service": ROLE,
        "message": os.getenv("APP_MESSAGE", "Kubernetes lab"),
        "payment_secret_configured": bool(os.getenv("PAYMENT_DEMO_KEY")) if ROLE == "payment" else None,
    }

@app.get("/")
def index(request: Request, fail: str = "", slow: str = ""):
    # This parent span makes the application's business operation easy to spot.
    with tracer.start_as_current_span(f"{ROLE}.handle_request") as span:
        span.set_attribute("demo.role", ROLE)
        if ROLE == "frontend":
            params = {}
            if fail:
                params["fail"] = fail
            if slow:
                params["slow"] = slow
            result = call_service("checkout", params=params)
            return {"service": ROLE, "result": result, "hint": "Open this request in Jaeger"}
        if ROLE == "checkout":
            # Separate spans run in the same trace because requests instrumentation propagates context.
            inventory = call_service("inventory")
            payment_params = {}
            # Read demo switches passed by frontend as query parameters.
            fail_target = request.query_params.get("fail", "")
            slow_target = request.query_params.get("slow", "")
            if fail_target:
                payment_params["fail"] = fail_target
            if slow_target:
                payment_params["slow"] = slow_target
            try:
                payment = call_service("payment", params=payment_params)
                return {"inventory": inventory, "payment": payment}
            except requests.HTTPError as exc:
                span.record_exception(exc)
                span.set_attribute("error", True)
                raise
        if ROLE == "inventory":
            with tracer.start_as_current_span("inventory.check_stock") as span:
                time.sleep(0.05)
                span.set_attribute("inventory.available", True)
                return {"available": True, "quantity": 17}
        if ROLE == "payment":
            if request.query_params.get("slow") == "payment":
                time.sleep(1.5)
            if request.query_params.get("fail") == "payment":
                with tracer.start_as_current_span("payment.authorize") as span:
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "simulated_payment_decline")
                    from fastapi import HTTPException
                    raise HTTPException(status_code=503, detail="Simulated payment failure")
            with tracer.start_as_current_span("payment.authorize") as span:
                span.set_attribute("payment.provider", "demo")
                time.sleep(0.08)
                return {"authorized": True, "transaction": f"demo-{random.randint(10000,99999)}"}
        return {"service": ROLE, "message": "Unknown ROLE"}
