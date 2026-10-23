import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from .models import AISystem, AISystemVersion, EvaluationRun
from .outcomes import Outcome, load_outcomes, pass_rate
from .security import Principal, principal

router = APIRouter(prefix="/api/v1")


class Side(BaseModel):
    run_id: uuid.UUID
    version: str
    pass_rate: float | None
    failed: int
    critical_failures: int
    open_reviews: int
    total: int


class Delta(BaseModel):
    case_key: str
    category: str
    severity: str
    question: str
    baseline: str
    candidate: str


class CategoryRow(BaseModel):
    category: str
    baseline: float | None
    candidate: float | None


class Comparison(BaseModel):
    system: str
    suite: str
    baseline: Side
    candidate: Side
    categories: list[CategoryRow]
    regressions: list[Delta]  # passed in baseline, fail in candidate
    fixed: list[Delta]  # failed in baseline, pass in candidate
    unchanged_failures: list[Delta]
    only_in_one: list[str]
    verdict: str  # worse | better | same
    critical_regressions: int


def _side(run: EvaluationRun, version: str, outs: list[Outcome]) -> Side:
    return Side(run_id=run.id, version=version, pass_rate=pass_rate(outs),
                failed=sum(1 for o in outs if o.effective == "failed"),
                critical_failures=sum(1 for o in outs if o.effective == "failed" and o.severity == "critical"),
                open_reviews=sum(1 for o in outs if o.open_review), total=len(outs))


@router.get("/compare", response_model=Comparison)
async def compare(baseline_run: uuid.UUID, candidate_run: uuid.UUID, p: Principal = Depends(principal)):
    s = p.session
    runs = {}
    for rid in (baseline_run, candidate_run):
        run = (await s.execute(select(EvaluationRun).where(EvaluationRun.id == rid))).scalar_one_or_none()
        if run is None:
            raise HTTPException(404, "Run not found")
        runs[rid] = run
    b, c = runs[baseline_run], runs[candidate_run]
    vers = {}
    for run in (b, c):
        v = (await s.execute(select(AISystemVersion, AISystem.name).join(AISystem, AISystem.id == AISystemVersion.system_id)
                             .where(AISystemVersion.id == run.system_version_id))).one()
        vers[run.id] = v
    if vers[b.id][0].system_id != vers[c.id][0].system_id:
        raise HTTPException(422, "Both runs must belong to the same application")
    if b.suite_id != c.suite_id:
        raise HTTPException(422, "Both runs must use the same test suite to be comparable")
    if "completed" not in (b.status,) or c.status != "completed":
        raise HTTPException(409, "Both runs must be completed")
    from .models import TestSuite
    suite = (await s.execute(select(TestSuite.name).where(TestSuite.id == b.suite_id))).scalar_one()
    ob, oc = await load_outcomes(p, b.id), await load_outcomes(p, c.id)
    mb, mc = {o.case_key: o for o in ob}, {o.case_key: o for o in oc}
    delta = lambda o, base, cand: Delta(case_key=o.case_key, category=o.category, severity=o.severity,  # noqa: E731
                                        question=o.question, baseline=base, candidate=cand)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    reg, fix, unch = [], [], []
    for k, cand in mc.items():
        base = mb.get(k)
        if base is None or "pending" in (base.effective, cand.effective):
            continue
        if base.effective == "passed" and cand.effective == "failed":
            reg.append(delta(cand, base.effective, cand.effective))
        elif base.effective == "failed" and cand.effective == "passed":
            fix.append(delta(cand, base.effective, cand.effective))
        elif base.effective == "failed" and cand.effective == "failed":
            unch.append(delta(cand, base.effective, cand.effective))
    for lst in (reg, fix, unch):
        lst.sort(key=lambda d: (order[d.severity], d.case_key))  # critical first
    cats = defaultdict(lambda: ([], []))
    for o in ob:
        cats[o.category][0].append(o)
    for o in oc:
        cats[o.category][1].append(o)
    categories = [CategoryRow(category=k, baseline=pass_rate(v[0]), candidate=pass_rate(v[1])) for k, v in sorted(cats.items())]
    sb, sc = _side(b, vers[b.id][0].version_label, ob), _side(c, vers[c.id][0].version_label, oc)
    crit_reg = sum(1 for d in reg if d.severity == "critical")
    # A critical regression makes the candidate worse whatever the average says.
    verdict = "worse" if (crit_reg or len(reg) > len(fix) or (sc.pass_rate or 0) < (sb.pass_rate or 0)) \
        else "better" if (len(fix) > len(reg) or (sc.pass_rate or 0) > (sb.pass_rate or 0)) else "same"
    return Comparison(system=vers[c.id][1], suite=suite, baseline=sb, candidate=sc, categories=categories, regressions=reg,
                      fixed=fix, unchanged_failures=unch, only_in_one=sorted(set(mb) ^ set(mc)), verdict=verdict,
                      critical_regressions=crit_reg)
