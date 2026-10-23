import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from . import audit
from .models import AuditLog, User
from .routes import router
from .compare import router as compare_router
from .gates import router as gates_router
from .reports import router as reports_router
from .reviews import router as reviews_router
from .runs import router as runs_router
from .suites import router as suites_router
from .security import Principal, require

import time

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQS = Counter("medguard_http_requests_total", "HTTP requests", ["method", "route", "status"])
LAT = Histogram("medguard_http_request_seconds", "HTTP request latency", ["route"])

app = FastAPI(title="MedGuard AI API", version="0.1.0", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
from . import telemetry

telemetry.setup(app)


@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")  # route template: no ids, bounded cardinality
    REQS.labels(request.method, route, str(response.status_code)).inc()
    LAT.labels(route).observe(time.perf_counter() - start)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
app.include_router(router)
app.include_router(suites_router)
app.include_router(runs_router)
app.include_router(reviews_router)
app.include_router(compare_router)
app.include_router(gates_router)
app.include_router(reports_router)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):  # never leak internals
    return JSONResponse({"type": "about:blank", "title": "Internal error", "status": 500}, status_code=500,
                        media_type="application/problem+json")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


class AuditEntry(BaseModel):
    id: int
    ts: str
    actor_id: uuid.UUID | None
    actor: str | None
    action: str
    entity_type: str
    entity_id: str
    detail: dict | None


@app.get("/api/v1/audit")
async def audit_list(limit: int = 100, before_id: int | None = None, action: str | None = None,
                     p: Principal = Depends(require("admin"))):
    limit = max(1, min(limit, 500))
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if before_id:
        q = q.where(AuditLog.id < before_id)
    if action:
        q = q.where(AuditLog.action.like(f"{action[:60]}%"))
    rows = (await p.session.execute(q)).scalars().all()
    users = {u.id: (u.display_name or u.email) for u in (await p.session.execute(select(User))).scalars()}
    ok, bad = await audit.verify_chain(p.session, p.org_id)
    return {"chain_valid": ok, "first_invalid_id": bad,
            "entries": [AuditEntry(id=r.id, ts=r.ts.isoformat(), actor_id=r.actor_id, actor=users.get(r.actor_id) if r.actor_id else None,
                                   action=r.action, entity_type=r.entity_type, entity_id=r.entity_id, detail=r.after) for r in rows]}
