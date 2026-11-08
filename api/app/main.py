import contextvars
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, make_asgi_app

from .errors import ApiError
from .routers import admin, health, payments, webhooks
from .schemas import error_envelope

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
log = logging.getLogger("payforge")

REQUESTS = Counter("payforge_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "payforge_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

app = FastAPI(
    title="PayForge",
    version="0.1.0",
    description="Multi-tenant payment platform: idempotent payments API, double-entry ledger, "
    "reliable webhooks.",
)
app.mount("/metrics", make_asgi_app())


@app.middleware("http")
async def observability(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
    request_id_var.set(rid)
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    route = getattr(request.scope.get("route"), "path", request.url.path)
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(elapsed)
    response.headers["X-Request-Id"] = rid
    if not request.url.path.startswith(("/metrics", "/health")):
        log.info("%s %s -> %s (%.1f ms)", request.method, request.url.path,
                 response.status_code, elapsed * 1000)
    return response


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(
        error_envelope(exc.code, exc.message), status_code=exc.status_code, headers=exc.headers
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        error_envelope("validation_error", "The request was invalid.", details), status_code=422
    )


app.include_router(health.router)
app.include_router(admin.router)
app.include_router(payments.router)
app.include_router(webhooks.router)
