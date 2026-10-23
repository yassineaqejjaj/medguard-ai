"""Medical Review Workspace API.

Rules:
  * only reviewers (and admins) record reviews; engineers cannot review their own campaigns;
  * reviews are append-only; a reviewer who changes their mind adds a new review, the latest per reviewer counts;
  * two reviewers who disagree make the case `disputed` until an admin arbitrates, with a recorded justification;
  * a critical failure is never closed by the machine: it stays pending until a human decision exists.
"""
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from . import audit
from .models import EvaluationRun, Review, ReviewResolution, RunItem, TestCase, User
from .runs import ItemOut, build_items
from .schemas import Severity
from .security import Principal, principal, require_roles

router = APIRouter(prefix="/api/v1")
ERROR_KINDS = ("citation_error", "unsupported_claim", "safety_issue", "out_of_scope", "technical", "other")


class Annotation(BaseModel):
    kind: Literal["citation_error", "unsupported_claim", "safety_issue", "out_of_scope", "technical", "other"]
    note: str = Field(min_length=1, max_length=1000)
    quote: str | None = Field(default=None, max_length=1000)


class ReviewIn(BaseModel):
    decision: Literal["accept", "reject"]  # accept: the response is acceptable; reject: it is not
    error_severity: Severity | None = None
    annotations: list[Annotation] = Field(default_factory=list, max_length=20)
    justification: str = Field(min_length=10, max_length=4000)

    @field_validator("justification")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("justification must not be blank")
        return v


class ReviewOut(BaseModel):
    id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer: str
    decision: str
    error_severity: str | None
    annotations: list
    justification: str
    created_at: datetime


class ReviewDetail(BaseModel):
    item: ItemOut
    run_label: str
    reviews: list[ReviewOut]
    status: str
    final_decision: str | None
    my_decision: str | None


async def _item(p: Principal, item_id: uuid.UUID) -> tuple[RunItem, TestCase]:
    row = (await p.session.execute(select(RunItem, TestCase).join(TestCase, TestCase.id == RunItem.test_case_id)
                                   .where(RunItem.id == item_id))).one_or_none()
    if row is None:
        raise HTTPException(404, "Run item not found")
    return row[0], row[1]


async def _latest_reviews(p: Principal, item_id: uuid.UUID) -> list[tuple[Review, User]]:
    rows = (await p.session.execute(select(Review, User).join(User, User.id == Review.reviewer_id)
                                    .where(Review.run_item_id == item_id).order_by(Review.created_at, Review.id))).all()
    latest: dict[uuid.UUID, tuple[Review, User]] = {}
    for r, u in rows:  # later rows overwrite earlier ones from the same reviewer
        latest[u.id] = (r, u)
    return list(latest.values())


def _review_out(r: Review, u: User) -> ReviewOut:
    return ReviewOut(id=r.id, reviewer_id=u.id, reviewer=u.display_name or u.email, decision=r.decision,
                     error_severity=r.error_severity, annotations=r.annotations, justification=r.justification,
                     created_at=r.created_at)


@router.get("/reviews/queue", response_model=list[ItemOut])
async def queue(status: Literal["pending", "disputed", "resolved", "all"] = "pending", run_id: uuid.UUID | None = None,
                p: Principal = Depends(principal)):
    s = p.session
    q = (select(RunItem, TestCase).join(TestCase, TestCase.id == RunItem.test_case_id).where(RunItem.needs_review.is_(True)))
    if run_id:
        q = q.where(RunItem.run_id == run_id)
    rows = (await s.execute(q)).all()
    items = await build_items(p, rows)
    want = {"pending": {"pending"}, "disputed": {"disputed"}, "resolved": {"agreed", "arbitrated"},
            "all": {"pending", "disputed", "agreed", "arbitrated"}}[status]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    out = [i for i in items if i.review_status in want]
    out.sort(key=lambda i: (order[i.severity], i.case_key))  # critical first
    return out


@router.get("/run-items/{item_id}/review", response_model=ReviewDetail)
async def review_detail(item_id: uuid.UUID, p: Principal = Depends(principal)):
    item, case = await _item(p, item_id)
    built = (await build_items(p, [(item, case)]))[0]
    run = (await p.session.execute(select(EvaluationRun).where(EvaluationRun.id == item.run_id))).scalar_one()
    reviews = await _latest_reviews(p, item_id)
    mine = next((r.decision for r, u in reviews if u.id == p.user_id), None)
    return ReviewDetail(item=built, run_label=str(run.id)[:8], reviews=[_review_out(r, u) for r, u in reviews],
                        status=built.review_status or "none", final_decision=built.human_decision, my_decision=mine)


async def _resolve(p: Principal, item_id: uuid.UUID) -> ReviewResolution:
    """Recompute agreement from the latest review per reviewer."""
    decisions = {r.decision for r, _ in await _latest_reviews(p, item_id)}
    res = (await p.session.execute(select(ReviewResolution).where(ReviewResolution.run_item_id == item_id))).scalar_one_or_none()
    if res is not None and res.status == "arbitrated":
        return res  # an arbitrated decision is final; later reviews do not reopen it silently
    status, final = ("agreed", next(iter(decisions))) if len(decisions) == 1 else ("disputed", None)
    if res is None:
        res = ReviewResolution(org_id=p.org_id, run_item_id=item_id, status=status, final_decision=final, resolved_by=None)
        p.session.add(res)
    else:
        res.status, res.final_decision = status, final
    await p.session.flush()
    return res


@router.post("/run-items/{item_id}/reviews", response_model=ReviewDetail, status_code=201)
async def submit_review(item_id: uuid.UUID, body: ReviewIn, p: Principal = Depends(require_roles("reviewer", "admin"))):
    item, case = await _item(p, item_id)
    if not item.needs_review:
        raise HTTPException(409, "This result was not flagged for human review")
    existing = (await p.session.execute(select(ReviewResolution).where(ReviewResolution.run_item_id == item_id))).scalar_one_or_none()
    if existing is not None and existing.status == "arbitrated":
        raise HTTPException(409, "This case has already been arbitrated")
    if body.decision == "reject" and body.error_severity is None:
        raise HTTPException(422, "error_severity is required when rejecting a response")
    if body.decision == "accept" and body.error_severity is not None:
        raise HTTPException(422, "error_severity only applies to a rejection")
    p.session.add(Review(org_id=p.org_id, run_item_id=item_id, reviewer_id=p.user_id, decision=body.decision,
                         error_severity=body.error_severity, annotations=[a.model_dump() for a in body.annotations],
                         justification=body.justification))
    await p.session.flush()
    res = await _resolve(p, item_id)
    await audit.record(p.session, p.org_id, p.user_id, "review.submit", "run_item", str(item_id),
                       after={"decision": body.decision, "error_severity": body.error_severity, "resolution": res.status,
                              "case": case.case_key, "severity": case.severity})
    return await review_detail(item_id, p)


class ArbitrateIn(BaseModel):
    final_decision: Literal["accept", "reject"]
    justification: str = Field(min_length=10, max_length=4000)


@router.post("/run-items/{item_id}/arbitrate", response_model=ReviewDetail)
async def arbitrate(item_id: uuid.UUID, body: ArbitrateIn, p: Principal = Depends(require_roles("admin"))):
    item, case = await _item(p, item_id)
    res = (await p.session.execute(select(ReviewResolution).where(ReviewResolution.run_item_id == item_id))).scalar_one_or_none()
    if res is None or res.status != "disputed":
        raise HTTPException(409, "Only a disputed case can be arbitrated")
    res.status, res.final_decision, res.resolved_by = "arbitrated", body.final_decision, p.user_id
    await audit.record(p.session, p.org_id, p.user_id, "review.arbitrate", "run_item", str(item_id),
                       after={"final_decision": body.final_decision, "justification": body.justification, "case": case.case_key})
    await p.session.flush()
    return await review_detail(item_id, p)


class AgreementOut(BaseModel):
    n: int
    observed: float | None
    kappa: float | None
    confusion: dict[str, int]
    judge_false_pass: int
    judge_false_fail: int
    sufficient: bool
    min_samples: int
    note: str


@router.get("/judge/agreement", response_model=AgreementOut)
async def judge_agreement(p: Principal = Depends(require_roles("reviewer", "admin"))):
    """Judge verdict vs final human decision, per reviewed item that had at least one judge criterion."""
    from .evaluation.agreement import MIN_SAMPLES, agreement
    from .models import CriterionResult
    res = (await p.session.execute(select(ReviewResolution).where(ReviewResolution.final_decision.is_not(None)))).scalars().all()
    pairs = []
    for r in res:
        judged = (await p.session.execute(select(CriterionResult.status).where(
            CriterionResult.run_item_id == r.run_item_id, CriterionResult.kind == "llm_judge", CriterionResult.status != "error"))).scalars().all()
        if judged:
            pairs.append(("fail" if "fail" in judged else "pass", "pass" if r.final_decision == "accept" else "fail"))
    a = agreement(pairs)
    note = ("Not enough human-reviewed cases to trust the judge: treat its scores as indicative." if not a.sufficient
            else "Agreement measured on enough cases; a false pass (judge pass, human reject) is the dangerous error.")
    return AgreementOut(**a.__dict__, min_samples=MIN_SAMPLES, note=note)
