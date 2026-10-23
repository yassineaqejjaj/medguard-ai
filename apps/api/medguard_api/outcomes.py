"""Effective outcomes: what a result counts as once humans have weighed in.

The automatic status stays on record. For gating and comparison a flagged result is judged by the resolved human
decision (accept = acceptable, reject = not acceptable); unresolved flagged results are 'open', never silently passed."""
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from .models import ReviewResolution, RunItem, TestCase
from .security import Principal

CLOSED = ("agreed", "arbitrated")


@dataclass
class Outcome:
    item_id: uuid.UUID
    case_key: str
    case_version: int
    category: str
    severity: str
    question: str
    auto_status: str  # passed | failed | error | pending
    effective: str  # passed | failed | pending
    needs_review: bool
    open_review: bool  # flagged and not yet closed by a human decision
    human_decision: str | None
    score: float | None = None


async def load_outcomes(p: Principal, run_id: uuid.UUID) -> list[Outcome]:
    rows = (await p.session.execute(select(RunItem, TestCase).join(TestCase, TestCase.id == RunItem.test_case_id)
                                    .where(RunItem.run_id == run_id))).all()
    res = {r.run_item_id: r for r in (await p.session.execute(
        select(ReviewResolution).where(ReviewResolution.run_item_id.in_([r[0].id for r in rows])))).scalars()} if rows else {}
    out = []
    for item, case in rows:
        r = res.get(item.id)
        closed = r is not None and r.status in CLOSED
        human = r.final_decision if closed else None
        if human == "accept":
            eff = "passed"
        elif human == "reject":
            eff = "failed"
        elif item.status in ("failed", "error"):
            eff = "failed"  # an application error is a failure to demonstrate the behaviour
        elif item.status == "passed":
            eff = "passed"
        else:
            eff = "pending"
        out.append(Outcome(item.id, case.case_key, case.version, case.category, case.severity, case.input, item.status, eff,
                           item.needs_review, item.needs_review and not closed, human))
    return out


def pass_rate(outs: list[Outcome]) -> float | None:
    done = [o for o in outs if o.effective != "pending"]
    return (sum(1 for o in done if o.effective == "passed") / len(done)) if done else None
