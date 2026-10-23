import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from . import audit
from .models import (AISystem, AISystemVersion, CriterionResult, EvaluationRun, ReviewResolution, RunItem, TestCase, TestSuite)
from .schemas import RunCreate
from .security import Principal, principal, require

router = APIRouter(prefix="/api/v1")


def enqueue(org_id: uuid.UUID, run_id: uuid.UUID) -> None:  # indirection so tests can run the engine inline
    from .worker import enqueue_run
    enqueue_run(org_id, run_id)


class RunOut(BaseModel):
    id: uuid.UUID
    system_id: uuid.UUID
    system_name: str
    version: str
    suite_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    total: int
    passed: int
    failed: int
    errors: int
    pending: int
    critical_failures: int
    needs_review: int
    pass_rate: float | None
    judge_model: str | None
    params: dict
    judge_prompt_versions: dict


async def _run_out(p: Principal, run: EvaluationRun) -> RunOut:
    s = p.session
    ver = (await s.execute(select(AISystemVersion).where(AISystemVersion.id == run.system_version_id))).scalar_one()
    sysm = (await s.execute(select(AISystem).where(AISystem.id == ver.system_id))).scalar_one()
    suite = (await s.execute(select(TestSuite).where(TestSuite.id == run.suite_id))).scalar_one()
    rows = (await s.execute(select(RunItem.status, RunItem.needs_review, TestCase.severity)
                            .join(TestCase, TestCase.id == RunItem.test_case_id).where(RunItem.run_id == run.id))).all()
    cnt = lambda st: sum(1 for r in rows if r[0] == st)  # noqa: E731
    passed, failed = cnt("passed"), cnt("failed")
    done = passed + failed + cnt("error")
    return RunOut(id=run.id, system_id=sysm.id, system_name=sysm.name, version=ver.version_label, suite_name=suite.name,
                  status=run.status, started_at=run.started_at, finished_at=run.finished_at, total=len(rows),
                  passed=passed, failed=failed, errors=cnt("error"), pending=cnt("pending"),
                  critical_failures=sum(1 for r in rows if r[0] == "failed" and r[2] == "critical"),
                  needs_review=sum(1 for r in rows if r[1]), pass_rate=(passed / done if done else None),
                  judge_model=run.judge_model, params=run.params, judge_prompt_versions=run.judge_prompt_versions)


@router.post("/runs", response_model=RunOut, status_code=201)
async def create_run(body: RunCreate, p: Principal = Depends(require("engineer"))):
    s = p.session
    ver = (await s.execute(select(AISystemVersion).where(AISystemVersion.id == body.system_version_id))).scalar_one_or_none()
    suite = (await s.execute(select(TestSuite).where(TestSuite.id == body.suite_id))).scalar_one_or_none()
    if ver is None or suite is None:
        raise HTTPException(404, "Application version or suite not found")
    cases = (await s.execute(select(TestCase).where(TestCase.suite_id == suite.id, TestCase.is_current,
                                                    TestCase.validation_status != "rejected")
                             .order_by(TestCase.position))).scalars().all()
    if not cases:
        raise HTTPException(422, "The suite has no runnable scenarios")
    run = EvaluationRun(org_id=p.org_id, system_version_id=ver.id, suite_id=suite.id, status="queued", params={},
                        judge_prompt_versions={}, started_by=p.user_id)
    s.add(run)
    await s.flush()
    for c in cases:  # the run pins the exact case versions it will execute
        s.add(RunItem(org_id=p.org_id, run_id=run.id, test_case_id=c.id, status="pending", needs_review=False,
                      review_reasons=[]))
    await audit.record(s, p.org_id, p.user_id, "run.create", "evaluation_run", str(run.id),
                       after={"system_version": str(ver.id), "suite": str(suite.id), "cases": len(cases)})
    await s.flush()
    out = await _run_out(p, run)
    enqueue(p.org_id, run.id)  # delayed a couple of seconds so this transaction has committed
    return out


@router.get("/runs", response_model=list[RunOut])
async def list_runs(limit: int = 50, p: Principal = Depends(principal)):
    limit = max(1, min(limit, 200))
    runs = (await p.session.execute(select(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(limit))).scalars()
    return [await _run_out(p, r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: uuid.UUID, p: Principal = Depends(principal)):
    run = (await p.session.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")
    return await _run_out(p, run)


class CriterionOut(BaseModel):
    kind: str
    criterion: str
    score: float | None
    status: str
    justification: str
    evidence: list
    confidence: float | None
    requires_review: bool
    judge_prompt_version: str | None


class ItemOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    case_key: str
    case_version: int
    category: str
    severity: str
    question: str
    status: str
    needs_review: bool
    review_reasons: list
    latency_ms: int | None
    response_text: str | None
    reference_context: str
    expected_behavior: str
    score: float | None
    review_status: str | None = None  # None: no review needed; pending | agreed | disputed | arbitrated
    human_decision: str | None = None  # accept | reject, once resolved
    criteria: list[CriterionOut]


async def build_items(p: Principal, rows: list) -> list[ItemOut]:
    s = p.session
    if not rows:
        return []
    results = (await s.execute(select(CriterionResult).where(CriterionResult.run_item_id.in_([r[0].id for r in rows]))
                               .order_by(CriterionResult.kind, CriterionResult.criterion))).scalars().all()
    by_item: dict[uuid.UUID, list[CriterionResult]] = {}
    for r in results:
        by_item.setdefault(r.run_item_id, []).append(r)
    res_rows = (await s.execute(select(ReviewResolution).where(ReviewResolution.run_item_id.in_([r[0].id for r in rows])))).scalars()
    resolutions = {r.run_item_id: r for r in res_rows}
    out = []
    for item, case in rows:
        crs = by_item.get(item.id, [])
        scores = [c.score for c in crs if c.score is not None]
        res = resolutions.get(item.id)
        out.append(ItemOut(
            id=item.id, run_id=item.run_id, case_key=case.case_key, case_version=case.version, category=case.category,
            severity=case.severity, question=case.input, status=item.status, needs_review=item.needs_review,
            review_reasons=item.review_reasons, latency_ms=item.latency_ms, response_text=item.response_text,
            reference_context=case.reference_context, expected_behavior=case.expected_behavior,
            score=(min(scores) if scores else None),  # weakest criterion: an average would let passes hide a failure
            review_status=(res.status if res else ("pending" if item.needs_review else None)),
            human_decision=(res.final_decision if res else None),
            criteria=[CriterionOut(kind=c.kind, criterion=c.criterion, score=c.score, status=c.status,
                                   justification=c.justification, evidence=c.evidence, confidence=c.confidence,
                                   requires_review=c.requires_review, judge_prompt_version=c.judge_prompt_version)
                      for c in crs]))
    return out


@router.get("/runs/{run_id}/items", response_model=list[ItemOut])
async def run_items(run_id: uuid.UUID, p: Principal = Depends(principal)):
    s = p.session
    if (await s.execute(select(EvaluationRun.id).where(EvaluationRun.id == run_id))).scalar_one_or_none() is None:
        raise HTTPException(404, "Run not found")
    rows = (await s.execute(select(RunItem, TestCase).join(TestCase, TestCase.id == RunItem.test_case_id)
                            .where(RunItem.run_id == run_id))).all()
    out = await build_items(p, rows)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    # failures first, critical before the rest, then by key — "critical first, nothing hidden"
    out.sort(key=lambda i: (i.status not in ("failed", "error"), order[i.severity], i.case_key))
    return out
