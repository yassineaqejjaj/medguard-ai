"""Release Gate: policy, evaluation, human release decision, and a CI/CD status endpoint.

Design rules:
  * blocking criteria are evaluated independently; a favourable average never masks a critical failure;
  * PASS is only returned when no blocking criterion fails AND no flagged result is still waiting for a human;
  * the gate never releases anything: a PASS is an input to an authorised person's recorded decision."""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from . import audit, ratelimit
from .db import sessionmaker, set_tenant
from .models import (AISystem, AISystemVersion, ApiToken, EvaluationRun, GateEvaluation, GatePolicy, ReleaseDecision,
                     ReviewResolution, User)
from .outcomes import Outcome, load_outcomes, pass_rate
from .security import Principal, principal, require, require_roles

router = APIRouter(prefix="/api/v1")


class GateRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_critical_failures: int = Field(default=0, ge=0)
    max_high_failures: int | None = Field(default=None, ge=0)
    min_pass_rate: float = Field(default=0.90, ge=0, le=1)
    min_category_pass_rate: dict[str, float] = Field(default_factory=dict)
    max_new_regressions: int | None = Field(default=None, ge=0)
    require_reviews_resolved: bool = True


class Criterion(BaseModel):
    name: str
    threshold: str
    value: str
    kind: Literal["blocking", "review"]
    status: Literal["pass", "fail", "review"]


def evaluate(outs: list[Outcome], rules: GateRules, regressions: int | None) -> tuple[str, dict]:
    crit_fail = [o for o in outs if o.effective == "failed" and o.severity == "critical"]
    high_fail = [o for o in outs if o.effective == "failed" and o.severity == "high"]
    rate = pass_rate(outs)
    criteria: list[Criterion] = []

    def add(name, threshold, value, ok, kind="blocking"):
        criteria.append(Criterion(name=name, threshold=threshold, value=value, kind=kind,
                                  status="pass" if ok else ("fail" if kind == "blocking" else "review")))

    add("Critical failures", f"≤ {rules.max_critical_failures}", str(len(crit_fail)), len(crit_fail) <= rules.max_critical_failures)
    if rules.max_high_failures is not None:
        add("High-severity failures", f"≤ {rules.max_high_failures}", str(len(high_fail)), len(high_fail) <= rules.max_high_failures)
    add("Overall pass rate", f"≥ {rules.min_pass_rate:.0%}", "—" if rate is None else f"{rate:.1%}",
        rate is not None and rate >= rules.min_pass_rate)
    for cat, floor in sorted(rules.min_category_pass_rate.items()):
        r = pass_rate([o for o in outs if o.category == cat])
        add(f"Category · {cat}", f"≥ {floor:.0%}", "—" if r is None else f"{r:.1%}", r is not None and r >= floor)
    if rules.max_new_regressions is not None and regressions is not None:
        add("New regressions vs baseline", f"≤ {rules.max_new_regressions}", str(regressions), regressions <= rules.max_new_regressions)
    open_reviews = [o for o in outs if o.open_review]
    if rules.require_reviews_resolved:
        add("Human reviews resolved", "0 open", f"{len(open_reviews)} open", not open_reviews, kind="review")

    if any(c.status == "fail" for c in criteria):
        status = "FAIL"
    elif any(c.status == "review" for c in criteria):
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"
    crit_tests = [{"case_key": o.case_key, "question": o.question, "effective": o.effective, "auto_status": o.auto_status,
                   "human_decision": o.human_decision, "open_review": o.open_review}
                  for o in outs if o.severity == "critical" and (o.effective == "failed" or o.needs_review)]
    details = {"criteria": [c.model_dump() for c in criteria], "counts": {
        "total": len(outs), "failed": sum(1 for o in outs if o.effective == "failed"), "critical_failures": len(crit_fail),
        "open_reviews": len(open_reviews), "pass_rate": rate}, "critical_tests": crit_tests}
    return status, details


# ---- policy ------------------------------------------------------------------------------

@router.get("/systems/{system_id}/gate-policy", response_model=GateRules)
async def get_policy(system_id: uuid.UUID, p: Principal = Depends(principal)):
    if (await p.session.execute(select(AISystem.id).where(AISystem.id == system_id))).scalar_one_or_none() is None:
        raise HTTPException(404, "Application not found")
    pol = (await p.session.execute(select(GatePolicy).where(GatePolicy.system_id == system_id))).scalar_one_or_none()
    return GateRules.model_validate(pol.rules) if pol else GateRules()


@router.put("/systems/{system_id}/gate-policy", response_model=GateRules)
async def put_policy(system_id: uuid.UUID, rules: GateRules, p: Principal = Depends(require_roles("admin"))):
    if (await p.session.execute(select(AISystem.id).where(AISystem.id == system_id))).scalar_one_or_none() is None:
        raise HTTPException(404, "Application not found")
    pol = (await p.session.execute(select(GatePolicy).where(GatePolicy.system_id == system_id))).scalar_one_or_none()
    before = pol.rules if pol else None
    if pol is None:
        p.session.add(GatePolicy(org_id=p.org_id, system_id=system_id, name="default", rules=rules.model_dump()))
    else:
        pol.rules = rules.model_dump()
    await audit.record(p.session, p.org_id, p.user_id, "gate.policy.update", "ai_system", str(system_id),
                       before=before, after=rules.model_dump())
    return rules


# ---- evaluation --------------------------------------------------------------------------

class EvalOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    baseline_run_id: uuid.UUID | None
    system_id: uuid.UUID
    system_name: str
    version: str
    status: str
    details: dict
    policy: dict
    evaluated_at: datetime
    is_latest: bool
    decisions: list[dict]


class EvalIn(BaseModel):
    baseline_run_id: uuid.UUID | None = None


async def _eval_out(p: Principal, g: GateEvaluation) -> EvalOut:
    s = p.session
    run = (await s.execute(select(EvaluationRun).where(EvaluationRun.id == g.run_id))).scalar_one()
    ver, name = (await s.execute(select(AISystemVersion, AISystem.name).join(AISystem, AISystem.id == AISystemVersion.system_id)
                                 .where(AISystemVersion.id == run.system_version_id))).one()
    latest = (await s.execute(select(GateEvaluation.id).where(GateEvaluation.run_id == g.run_id)
                              .order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.id.desc()).limit(1))).scalar_one()
    decs = (await s.execute(select(ReleaseDecision, User).join(User, User.id == ReleaseDecision.decided_by)
                            .where(ReleaseDecision.gate_evaluation_id == g.id).order_by(ReleaseDecision.ts))).all()
    return EvalOut(id=g.id, run_id=g.run_id, baseline_run_id=g.baseline_run_id, system_id=ver.system_id, system_name=name,
                   version=ver.version_label, status=g.status, details=g.details, policy=g.policy_snapshot,
                   evaluated_at=g.evaluated_at, is_latest=(latest == g.id),
                   decisions=[{"decision": d.decision, "justification": d.justification, "by": u.display_name or u.email,
                               "at": d.ts.isoformat()} for d, u in decs])


@router.post("/runs/{run_id}/gate", response_model=EvalOut, status_code=201)
async def evaluate_gate(run_id: uuid.UUID, body: EvalIn, p: Principal = Depends(require("engineer"))):
    s = p.session
    run = (await s.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status != "completed":
        raise HTTPException(409, "The run must be completed before its gate can be evaluated")
    ver = (await s.execute(select(AISystemVersion).where(AISystemVersion.id == run.system_version_id))).scalar_one()
    pol = (await s.execute(select(GatePolicy).where(GatePolicy.system_id == ver.system_id))).scalar_one_or_none()
    rules = GateRules.model_validate(pol.rules) if pol else GateRules()
    regressions = None
    if body.baseline_run_id:
        from .compare import compare
        cmp = await compare(body.baseline_run_id, run_id, p)
        regressions = len(cmp.regressions)
    status, details = evaluate(await load_outcomes(p, run_id), rules, regressions)
    g = GateEvaluation(org_id=p.org_id, run_id=run_id, baseline_run_id=body.baseline_run_id,
                       policy_snapshot=rules.model_dump(), status=status, details=details)
    s.add(g)
    await s.flush()
    await s.refresh(g)
    await audit.record(s, p.org_id, p.user_id, "gate.evaluate", "gate_evaluation", str(g.id),
                       after={"run": str(run_id), "status": status})
    return await _eval_out(p, g)


@router.get("/runs/{run_id}/gate", response_model=EvalOut | None)
async def latest_gate(run_id: uuid.UUID, p: Principal = Depends(principal)):
    g = (await p.session.execute(select(GateEvaluation).where(GateEvaluation.run_id == run_id)
                                 .order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.id.desc()).limit(1))).scalar_one_or_none()
    if g is None:
        return None  # not gated yet is a normal state, not an error
    return await _eval_out(p, g)


class GateRow(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    system_name: str
    version: str
    status: str
    evaluated_at: datetime
    decision: str | None


@router.get("/gates", response_model=list[GateRow])
async def list_gates(p: Principal = Depends(principal)):
    s = p.session
    rows = (await s.execute(select(GateEvaluation).order_by(GateEvaluation.evaluated_at.desc()).limit(200))).scalars().all()
    seen, out = set(), []
    for g in rows:  # latest evaluation per run
        if g.run_id in seen:
            continue
        seen.add(g.run_id)
        e = await _eval_out(p, g)
        out.append(GateRow(id=g.id, run_id=g.run_id, system_name=e.system_name, version=e.version, status=g.status,
                           evaluated_at=g.evaluated_at, decision=(e.decisions[-1]["decision"] if e.decisions else None)))
    return out


@router.get("/gates/{gate_id}", response_model=EvalOut)
async def get_gate(gate_id: uuid.UUID, p: Principal = Depends(principal)):
    g = (await p.session.execute(select(GateEvaluation).where(GateEvaluation.id == gate_id))).scalar_one_or_none()
    if g is None:
        raise HTTPException(404, "Gate evaluation not found")
    return await _eval_out(p, g)


class DecisionIn(BaseModel):
    decision: Literal["release", "block"]
    justification: str = Field(min_length=10, max_length=4000)


@router.post("/gates/{gate_id}/decision", response_model=EvalOut, status_code=201)
async def decide(gate_id: uuid.UUID, body: DecisionIn, p: Principal = Depends(require_roles("admin"))):
    """The release decision is a human act, recorded under the signer's name and never edited."""
    g = (await p.session.execute(select(GateEvaluation).where(GateEvaluation.id == gate_id))).scalar_one_or_none()
    if g is None:
        raise HTTPException(404, "Gate evaluation not found")
    if not (await _eval_out(p, g)).is_latest:
        raise HTTPException(409, "A newer gate evaluation exists for this run; decide on the latest one")
    if body.decision == "release" and g.status != "PASS":
        raise HTTPException(409, f"A release cannot be signed off while the gate status is {g.status}")
    if (await p.session.execute(select(ReleaseDecision.id).where(ReleaseDecision.gate_evaluation_id == g.id))).first():
        raise HTTPException(409, "A decision has already been recorded for this evaluation")
    p.session.add(ReleaseDecision(org_id=p.org_id, gate_evaluation_id=g.id, decided_by=p.user_id, decision=body.decision,
                                  justification=body.justification))
    await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "release.decision", "gate_evaluation", str(g.id),
                       after={"decision": body.decision, "gate_status": g.status, "justification": body.justification})
    return await _eval_out(p, g)


# ---- CI/CD tokens and status -------------------------------------------------------------

class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    id: uuid.UUID
    name: str
    scopes: list
    created_at: datetime | None = None
    last_used_at: datetime | None


@router.post("/tokens", status_code=201)
async def create_token(body: TokenCreate, p: Principal = Depends(require_roles("admin"))):
    raw = "mgt_" + secrets.token_urlsafe(32)
    t = ApiToken(org_id=p.org_id, name=body.name, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                 scopes=["gate:read"], created_by=p.user_id)
    p.session.add(t)
    await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "token.create", "api_token", str(t.id), after={"name": body.name})
    return {"id": str(t.id), "name": t.name, "token": raw, "note": "Shown once; only a hash is stored."}


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(p: Principal = Depends(require_roles("admin"))):
    rows = (await p.session.execute(select(ApiToken).order_by(ApiToken.name))).scalars()
    return [TokenOut(id=t.id, name=t.name, scopes=t.scopes, last_used_at=t.last_used_at) for t in rows]


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(token_id: uuid.UUID, p: Principal = Depends(require_roles("admin"))):
    t = (await p.session.execute(select(ApiToken).where(ApiToken.id == token_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Token not found")
    await p.session.delete(t)
    await audit.record(p.session, p.org_id, p.user_id, "token.revoke", "api_token", str(token_id), before={"name": t.name})


async def ci_principal(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer mgt_"):
        raise HTTPException(401, "A MedGuard CI token is required")
    h = hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest()
    async with sessionmaker()() as session:
        async with session.begin():
            org_id = (await session.execute(text("SELECT org_id_by_token_hash(:h)"), {"h": h})).scalar_one_or_none()
            if org_id is None:
                raise HTTPException(401, "Invalid token")
            await set_tenant(session, org_id)
            tok = (await session.execute(select(ApiToken).where(ApiToken.token_hash == h))).scalar_one()
            if "gate:read" not in tok.scopes:
                raise HTTPException(403, "Token lacks the gate:read scope")
            tok.last_used_at = datetime.now(timezone.utc)
            await ratelimit.check(f"token:{tok.id}")
            yield Principal(tok.id, org_id, "ci", f"token:{tok.name}", session)


EXIT = {"PASS": 0, "FAIL": 1, "REVIEW_REQUIRED": 2, "NOT_EVALUATED": 3}


@router.get("/ci/gate")
async def ci_gate(system: str, version: str, p: Principal = Depends(ci_principal)):
    """Latest gate status for an application version, shaped for a pipeline (map exit_code in the job)."""
    s = p.session
    row = (await s.execute(select(AISystemVersion, AISystem).join(AISystem, AISystem.id == AISystemVersion.system_id)
                           .where(AISystem.name == system, AISystemVersion.version_label == version))).one_or_none()
    if row is None:
        raise HTTPException(404, "Unknown application or version")
    g = (await s.execute(select(GateEvaluation).join(EvaluationRun, EvaluationRun.id == GateEvaluation.run_id)
                         .where(EvaluationRun.system_version_id == row[0].id)
                         .order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.id.desc()).limit(1))).scalar_one_or_none()
    if g is None:
        return {"status": "NOT_EVALUATED", "exit_code": EXIT["NOT_EVALUATED"], "reasons": ["No gate evaluation exists for this version"]}
    reasons = [f"{c['name']}: {c['value']} (required {c['threshold']})" for c in g.details["criteria"] if c["status"] != "pass"]
    dec = (await s.execute(select(ReleaseDecision).where(ReleaseDecision.gate_evaluation_id == g.id))).scalar_one_or_none()
    return {"status": g.status, "exit_code": EXIT[g.status], "run_id": str(g.run_id), "evaluated_at": g.evaluated_at.isoformat(),
            "reasons": reasons, "release_decision": dec.decision if dec else None,
            "note": "A PASS is not a certification; the release decision stays with an authorised person."}
