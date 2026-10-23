import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from . import audit
from .crypto import encrypt_secret
from .models import (AISystem, User, AISystemVersion, EvaluationRun, Organization, ReviewResolution, RunItem, TestCase)
from .security import Principal, principal, require

router = APIRouter(prefix="/api/v1")


# ---- /me ---------------------------------------------------------------------------------

class Me(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    org_name: str
    email: str
    display_name: str
    role: str


@router.get("/me", response_model=Me)
async def me(p: Principal = Depends(principal)):
    org = (await p.session.execute(select(Organization))).scalar_one()
    user = (await p.session.execute(select(User).where(User.id == p.user_id))).scalar_one()
    return Me(id=p.user_id, org_id=p.org_id, org_name=org.name, email=p.email,
              display_name=user.display_name or p.email, role=p.role)


# ---- AI systems --------------------------------------------------------------------------

class SystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    purpose: str = Field(default="", max_length=2000)
    usage_context: str = Field(default="", max_length=2000)
    owner: str = Field(default="", max_length=200)
    model_name: str | None = Field(default=None, max_length=200)
    version_label: str = Field(min_length=1, max_length=80)
    endpoint_url: str = Field(max_length=2000)
    auth_type: Literal["none", "bearer"] = "none"
    auth_secret: str | None = Field(default=None, max_length=4000)
    timeout_s: float = Field(default=30.0, gt=0, le=300)

    @field_validator("endpoint_url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        u = urlparse(v)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("endpoint_url must be an absolute http(s) URL")
        if u.username or u.password:
            raise ValueError("credentials must not be embedded in the URL")
        return v


class SystemOut(BaseModel):
    id: uuid.UUID
    name: str
    purpose: str
    owner: str
    model_name: str | None
    latest_version: str | None
    latest_version_id: uuid.UUID | None
    created_at: datetime
    last_run_at: datetime | None
    run_count: int


async def _system_rows(p: Principal, system_id: uuid.UUID | None = None) -> list[SystemOut]:
    q = select(AISystem).order_by(AISystem.created_at.desc())
    if system_id:
        q = q.where(AISystem.id == system_id)
    out = []
    for s in (await p.session.execute(q)).scalars():
        ver = (await p.session.execute(select(AISystemVersion.version_label, AISystemVersion.id)
                                       .where(AISystemVersion.system_id == s.id)
                                       .order_by(AISystemVersion.created_at.desc()).limit(1))).one_or_none()
        runs = (await p.session.execute(
            select(func.count(), func.max(EvaluationRun.started_at)).select_from(EvaluationRun)
            .join(AISystemVersion, AISystemVersion.id == EvaluationRun.system_version_id)
            .where(AISystemVersion.system_id == s.id))).one()
        out.append(SystemOut(id=s.id, name=s.name, purpose=s.purpose, owner=s.owner, model_name=s.model_name,
                             latest_version=ver[0] if ver else None, latest_version_id=ver[1] if ver else None, created_at=s.created_at, last_run_at=runs[1], run_count=runs[0]))
    return out


@router.get("/systems", response_model=list[SystemOut])
async def list_systems(p: Principal = Depends(principal)):
    return await _system_rows(p)


@router.post("/systems", response_model=SystemOut, status_code=201)
async def create_system(body: SystemCreate, p: Principal = Depends(require("engineer"))):
    if body.auth_type == "bearer" and not body.auth_secret:
        raise HTTPException(422, "auth_secret is required for bearer authentication")
    dup = (await p.session.execute(select(AISystem.id).where(AISystem.name == body.name))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, "An application with this name already exists")
    system = AISystem(org_id=p.org_id, name=body.name, description=body.description, purpose=body.purpose,
                      usage_context=body.usage_context, owner=body.owner, model_name=body.model_name, doc_sources=[])
    p.session.add(system)
    await p.session.flush()
    p.session.add(AISystemVersion(
        org_id=p.org_id, system_id=system.id, version_label=body.version_label, endpoint_url=body.endpoint_url,
        auth_type=body.auth_type, request_template={}, response_mapping={}, timeout_s=body.timeout_s,
        auth_secret_enc=encrypt_secret(body.auth_secret) if body.auth_type == "bearer" and body.auth_secret else None))
    # The secret itself is never written to the audit trail.
    await audit.record(p.session, p.org_id, p.user_id, "system.create", "ai_system", str(system.id),
                       after={"name": body.name, "version": body.version_label, "endpoint_url": body.endpoint_url,
                              "auth_type": body.auth_type})
    await p.session.flush()
    return (await _system_rows(p, system.id))[0]


class VersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=80)
    endpoint_url: str = Field(max_length=2000)
    auth_type: Literal["none", "bearer"] = "none"
    auth_secret: str | None = Field(default=None, max_length=4000)
    timeout_s: float = Field(default=30.0, gt=0, le=300)

    _check_url = field_validator("endpoint_url")(SystemCreate._http_url.__func__)  # type: ignore[attr-defined]


class VersionOut(BaseModel):
    id: uuid.UUID
    system_id: uuid.UUID
    system_name: str
    version_label: str
    endpoint_url: str
    auth_type: str
    created_at: datetime
    run_count: int
    last_run_at: datetime | None


async def _version_rows(p: Principal, system_id: uuid.UUID | None = None) -> list[VersionOut]:
    q = (select(AISystemVersion, AISystem.name).join(AISystem, AISystem.id == AISystemVersion.system_id)
         .order_by(AISystem.name, AISystemVersion.created_at))
    if system_id:
        q = q.where(AISystemVersion.system_id == system_id)
    out = []
    for v, name in (await p.session.execute(q)).all():
        n, last = (await p.session.execute(select(func.count(), func.max(EvaluationRun.started_at))
                                           .where(EvaluationRun.system_version_id == v.id))).one()
        out.append(VersionOut(id=v.id, system_id=v.system_id, system_name=name, version_label=v.version_label,
                              endpoint_url=v.endpoint_url, auth_type=v.auth_type, created_at=v.created_at,
                              run_count=n, last_run_at=last))
    return out


@router.get("/versions", response_model=list[VersionOut])
async def list_versions(system_id: uuid.UUID | None = None, p: Principal = Depends(principal)):
    return await _version_rows(p, system_id)


@router.post("/systems/{system_id}/versions", response_model=VersionOut, status_code=201)
async def add_version(system_id: uuid.UUID, body: VersionCreate, p: Principal = Depends(require("engineer"))):
    if (await p.session.execute(select(AISystem.id).where(AISystem.id == system_id))).scalar_one_or_none() is None:
        raise HTTPException(404, "Application not found")
    if body.auth_type == "bearer" and not body.auth_secret:
        raise HTTPException(422, "auth_secret is required for bearer authentication")
    if (await p.session.execute(select(AISystemVersion.id).where(AISystemVersion.system_id == system_id,
                                                                  AISystemVersion.version_label == body.version_label))).scalar_one_or_none():
        raise HTTPException(409, "This version label already exists for the application")
    v = AISystemVersion(org_id=p.org_id, system_id=system_id, version_label=body.version_label,
                        endpoint_url=body.endpoint_url, auth_type=body.auth_type, request_template={}, response_mapping={},
                        timeout_s=body.timeout_s,
                        auth_secret_enc=encrypt_secret(body.auth_secret) if body.auth_type == "bearer" and body.auth_secret else None)
    p.session.add(v)
    await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "system.version.add", "ai_system_version", str(v.id),
                       after={"system": str(system_id), "version": body.version_label, "endpoint_url": body.endpoint_url})
    return next(x for x in await _version_rows(p, system_id) if x.id == v.id)


# ---- Dashboard ---------------------------------------------------------------------------

class Summary(BaseModel):
    systems: int
    runs: int
    runs_last_30d: int
    pass_rate: float | None  # None until at least one test result exists
    tests_evaluated: int
    critical_failures: int
    pending_reviews: int
    never_evaluated: list[str]
    by_severity: dict[str, int]  # failed tests per severity
    recent_runs: list[dict]
    pass_rate_by_release: list[dict]  # latest completed run per application version


@router.get("/dashboard/summary", response_model=Summary)
async def dashboard_summary(p: Principal = Depends(principal)):
    s = p.session
    systems = (await s.execute(select(func.count()).select_from(AISystem))).scalar_one()
    runs = (await s.execute(select(func.count()).select_from(EvaluationRun))).scalar_one()
    since = datetime.now(timezone.utc) - timedelta(days=30)
    runs30 = (await s.execute(select(func.count()).select_from(EvaluationRun)
                              .where(EvaluationRun.started_at >= since))).scalar_one()
    passed = (await s.execute(select(func.count()).select_from(RunItem).where(RunItem.status == "passed"))).scalar_one()
    failed = (await s.execute(select(func.count()).select_from(RunItem)
                              .where(RunItem.status.in_(["failed", "error"])))).scalar_one()
    crit = (await s.execute(select(func.count()).select_from(RunItem).join(TestCase, TestCase.id == RunItem.test_case_id)
                            .where(RunItem.status == "failed", TestCase.severity == "critical"))).scalar_one()
    pending = (await s.execute(
        select(func.count()).select_from(RunItem)
        .outerjoin(ReviewResolution, ReviewResolution.run_item_id == RunItem.id)
        .where(RunItem.needs_review.is_(True),
               (ReviewResolution.id.is_(None)) | (ReviewResolution.status == "disputed")))).scalar_one()
    unevaluated = (await s.execute(
        select(AISystem.name).where(~select(EvaluationRun.id).join(
            AISystemVersion, AISystemVersion.id == EvaluationRun.system_version_id)
            .where(AISystemVersion.system_id == AISystem.id).exists()).order_by(AISystem.name))).scalars().all()
    total = passed + failed
    sev_rows = (await s.execute(select(TestCase.severity, func.count()).select_from(RunItem)
                                .join(TestCase, TestCase.id == RunItem.test_case_id).where(RunItem.status == "failed")
                                .group_by(TestCase.severity))).all()
    by_sev = {k: 0 for k in ("critical", "high", "medium", "low")} | {k: v for k, v in sev_rows}
    from .runs import _run_out
    recent = (await s.execute(select(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(50))).scalars().all()
    outs = [await _run_out(p, r) for r in recent]
    seen, by_release = set(), []
    for o in outs:  # newest first: keep the latest completed run per (system, version)
        key = (o.system_id, o.version)
        if o.status == "completed" and o.pass_rate is not None and key not in seen:
            seen.add(key)
            by_release.append({"system": o.system_name, "version": o.version, "pass_rate": o.pass_rate,
                               "started_at": o.started_at.isoformat(), "run_id": str(o.id)})
    by_release.sort(key=lambda r: r["started_at"])
    return Summary(systems=systems, runs=runs, runs_last_30d=runs30, pass_rate=(passed / total if total else None),
                   tests_evaluated=total, critical_failures=crit, pending_reviews=pending,
                   never_evaluated=list(unevaluated), by_severity=by_sev,
                   recent_runs=[{"id": str(o.id), "system": o.system_name, "version": o.version, "suite": o.suite_name,
                                 "status": o.status, "started_at": o.started_at.isoformat(), "pass_rate": o.pass_rate,
                                 "critical_failures": o.critical_failures} for o in outs[:5]],
                   pass_rate_by_release=by_release)
