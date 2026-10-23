"""Evidence Center: report generation (HTML / JSON / PDF), evidence listing, retention and settings."""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from jinja2 import Environment, select_autoescape
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from . import audit
from .models import (AISystem, AISystemVersion, AuditLog, CriterionResult, EvaluationRun, EvidenceObject, GateEvaluation,
                     Organization, Report, Review, ReviewResolution, RunItem, TestCase, TestSuite, User)
from .security import Principal, principal, require, require_roles
from .storage import IntegrityError, evidence_key, get_store, read_verified, sha256

router = APIRouter(prefix="/api/v1")
DISCLAIMER = ("A PASS means a version met the criteria configured for its campaign. It is not a guarantee of clinical "
              "safety, a medical-device or regulatory certification, and it does not replace medical experts. "
              "All content was produced with synthetic data unless the organisation states otherwise.")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


async def build_report(p: Principal, run_id: uuid.UUID) -> dict:
    s = p.session
    run = (await s.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")
    org = (await s.execute(select(Organization))).scalar_one()
    ver, sysm = (await s.execute(select(AISystemVersion, AISystem).join(AISystem, AISystem.id == AISystemVersion.system_id)
                                 .where(AISystemVersion.id == run.system_version_id))).one()
    suite = (await s.execute(select(TestSuite).where(TestSuite.id == run.suite_id))).scalar_one()
    starter = (await s.execute(select(User).where(User.id == run.started_by))).scalar_one_or_none() if run.started_by else None
    rows = (await s.execute(select(RunItem, TestCase).join(TestCase, TestCase.id == RunItem.test_case_id)
                            .where(RunItem.run_id == run_id).order_by(TestCase.case_key))).all()
    item_ids = [r[0].id for r in rows]
    crit = (await s.execute(select(CriterionResult).where(CriterionResult.run_item_id.in_(item_ids)))).scalars().all() if item_ids else []
    crit_by: dict = {}
    for c in crit:
        crit_by.setdefault(c.run_item_id, []).append(c)
    revs = (await s.execute(select(Review, User).join(User, User.id == Review.reviewer_id)
                            .where(Review.run_item_id.in_(item_ids)).order_by(Review.created_at))).all() if item_ids else []
    rev_by: dict = {}
    for r, u in revs:
        rev_by.setdefault(r.run_item_id, []).append({"reviewer": u.display_name or u.email, "decision": r.decision,
            "error_severity": r.error_severity, "justification": r.justification, "annotations": r.annotations, "at": r.created_at.isoformat()})
    ress = {r.run_item_id: r for r in (await s.execute(select(ReviewResolution).where(ReviewResolution.run_item_id.in_(item_ids)))).scalars()} if item_ids else {}
    evid = {e.id: e for e in (await s.execute(select(EvidenceObject).where(EvidenceObject.run_id == run_id, EvidenceObject.kind == "response"))).scalars()}

    scenarios, passed, failed, crit_fail, open_rev = [], 0, 0, 0, 0
    for item, case in rows:
        res = ress.get(item.id)
        closed = res is not None and res.status in ("agreed", "arbitrated")
        eff = ("passed" if res.final_decision == "accept" else "failed") if closed and res.final_decision else \
            ("failed" if item.status in ("failed", "error") else item.status)
        passed += eff == "passed"
        failed += eff == "failed"
        crit_fail += eff == "failed" and case.severity == "critical"
        open_rev += bool(item.needs_review and not closed)
        ev = evid.get(item.response_evidence_id)
        scenarios.append({
            "case_key": case.case_key, "case_version": case.version, "category": case.category, "severity": case.severity,
            "question": case.input, "expected_behavior": case.expected_behavior, "reference_context": case.reference_context,
            "automatic_status": item.status, "effective_outcome": eff, "needs_review": item.needs_review,
            "review_reasons": item.review_reasons, "latency_ms": item.latency_ms,
            "response_evidence": {"id": str(ev.id), "sha256": ev.sha256, "key": ev.s3_key} if ev else None,
            "criteria": [{"kind": c.kind, "criterion": c.criterion, "score": c.score, "status": c.status, "justification": c.justification,
                          "confidence": c.confidence, "judge_prompt_version": c.judge_prompt_version} for c in crit_by.get(item.id, [])],
            "reviews": rev_by.get(item.id, []),
            "resolution": {"status": res.status, "final_decision": res.final_decision} if res else None})
    gates = (await s.execute(select(GateEvaluation).where(GateEvaluation.run_id == run_id).order_by(GateEvaluation.evaluated_at))).scalars().all()
    from .gates import _eval_out
    gate_blocks = [(await _eval_out(p, g)).model_dump(mode="json") for g in gates]
    related = {str(run_id), *map(str, item_ids), *[str(g.id) for g in gates]}
    entries = (await s.execute(select(AuditLog).where(AuditLog.entity_id.in_(related)).order_by(AuditLog.id))).scalars().all()
    ok, bad = await audit.verify_chain(s, p.org_id)
    head = (await s.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1))).scalar_one_or_none()
    done = passed + failed
    return {
        "schema": "medguard.report/1", "generated_at": datetime.now(timezone.utc).isoformat(), "generated_by": p.email,
        "organisation": org.name,
        "run": {"id": str(run.id), "status": run.status, "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None, "started_by": (starter.display_name or starter.email) if starter else None,
                "application": sysm.name, "version": ver.version_label, "endpoint": ver.endpoint_url,
                "suite": suite.name, "parameters": run.params, "judge_model": run.judge_model, "judge_model_digest": run.judge_model_digest,
                "judge_prompt_versions": run.judge_prompt_versions},
        "summary": {"total": len(rows), "passed": passed, "failed": failed, "pass_rate": (passed / done if done else None),
                    "critical_failures": crit_fail, "open_reviews": open_rev},
        "scenarios": scenarios, "gates": gate_blocks,
        "audit": {"chain_valid": ok, "first_invalid_id": bad, "chain_head": head,
                  "entries": [{"id": e.id, "ts": e.ts.isoformat(), "action": e.action, "entity": f"{e.entity_type}:{e.entity_id}", "actor": str(e.actor_id) if e.actor_id else None, "hash": e.hash} for e in entries]},
        "disclaimer": DISCLAIMER}


_env = Environment(autoescape=select_autoescape(default=True, default_for_string=True))  # app output is untrusted: always escaped
HTML = _env.from_string("""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>MedGuard report {{ r.run.id[:8] }}</title>
<style>
body{font:13px/1.5 Inter,system-ui,sans-serif;color:#0b1220;margin:32px;max-width:1000px}
h1{font-size:24px;margin:0}h2{font-size:16px;margin:28px 0 8px;border-bottom:1px solid #e2e8f0;padding-bottom:4px}
table{border-collapse:collapse;width:100%;margin:6px 0}th,td{border:1px solid #e2e8f0;padding:5px 8px;text-align:left;vertical-align:top}th{background:#f1f5f9}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all}.mu{color:#475569}
.fail{color:#b91c1c;font-weight:600}.ok{color:#15803d;font-weight:600}.warn{color:#b45309;font-weight:600}
.box{border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;margin:8px 0}
</style></head><body>
<h1>MedGuard AI · Evaluation evidence report</h1>
<p class="mu">{{ r.organisation }} · generated {{ r.generated_at }} by {{ r.generated_by }}</p>
<div class="box"><strong>{{ r.run.application }} {{ r.run.version }}</strong> · suite {{ r.run.suite }}<br>
Run <span class="mono">{{ r.run.id }}</span> · {{ r.run.status }} · {{ r.run.started_at }} → {{ r.run.finished_at or "—" }} · started by {{ r.run.started_by or "—" }}<br>
Endpoint <span class="mono">{{ r.run.endpoint }}</span></div>
<h2>Summary</h2>
<table><tr><th>Tests</th><th>Passed</th><th>Failed</th><th>Pass rate</th><th>Critical failures</th><th>Open reviews</th></tr>
<tr><td>{{ r.summary.total }}</td><td>{{ r.summary.passed }}</td><td>{{ r.summary.failed }}</td>
<td>{{ "%.1f%%"|format(r.summary.pass_rate*100) if r.summary.pass_rate is not none else "—" }}</td>
<td class="{{ 'fail' if r.summary.critical_failures else '' }}">{{ r.summary.critical_failures }}</td><td>{{ r.summary.open_reviews }}</td></tr></table>
<h2>Evaluation configuration</h2>
<table><tr><th>Judge model</th><td>{{ r.run.judge_model or "none configured (judge criteria routed to human review)" }}</td></tr>
<tr><th>Judge model digest</th><td class="mono">{{ r.run.judge_model_digest or "—" }}</td></tr>
<tr><th>Judge prompt versions</th><td>{{ r.run.judge_prompt_versions }}</td></tr>
<tr><th>Parameters</th><td class="mono">{{ r.run.parameters }}</td></tr></table>
<h2>Release gate</h2>
{% for g in r.gates %}<div class="box"><strong class="{{ 'ok' if g.status=='PASS' else ('fail' if g.status=='FAIL' else 'warn') }}">{{ g.status }}</strong> · evaluated {{ g.evaluated_at }} <span class="mu">({{ g.id }})</span>
<table><tr><th>Criterion</th><th>Threshold</th><th>Result</th><th>Status</th></tr>
{% for c in g.details.criteria %}<tr><td>{{ c.name }}</td><td>{{ c.threshold }}</td><td>{{ c.value }}</td><td>{{ c.status }}</td></tr>{% endfor %}</table>
{% for d in g.decisions %}<div>Decision: <strong>{{ d.decision }}</strong> by {{ d.by }} at {{ d.at }} — {{ d.justification }}</div>{% endfor %}
</div>{% else %}<p class="mu">No gate evaluation recorded for this run.</p>{% endfor %}
<h2>Scenarios</h2>
{% for s in r.scenarios %}<div class="box">
<strong class="mono">{{ s.case_key }} v{{ s.case_version }}</strong> · {{ s.category }} · severity {{ s.severity }} ·
<span class="{{ 'ok' if s.effective_outcome=='passed' else 'fail' }}">{{ s.effective_outcome }}</span> <span class="mu">(automatic: {{ s.automatic_status }})</span><br>
<em>{{ s.question }}</em><br>
{% if s.response_evidence %}<span class="mu">Response evidence</span> <span class="mono">sha256:{{ s.response_evidence.sha256 }}</span><br>{% endif %}
<table><tr><th>Criterion</th><th>Kind</th><th>Status</th><th>Justification</th></tr>
{% for c in s.criteria %}<tr><td>{{ c.criterion }}</td><td>{{ c.kind }}{% if c.judge_prompt_version %} ({{ c.judge_prompt_version }}){% endif %}</td><td>{{ c.status }}</td><td>{{ c.justification }}</td></tr>{% endfor %}</table>
{% for rv in s.reviews %}<div>Review by <strong>{{ rv.reviewer }}</strong>: {{ rv.decision }}{% if rv.error_severity %} ({{ rv.error_severity }}){% endif %} — {{ rv.justification }}</div>{% endfor %}
{% if s.resolution %}<div class="mu">Resolution: {{ s.resolution.status }}{% if s.resolution.final_decision %} → {{ s.resolution.final_decision }}{% endif %}</div>{% endif %}
</div>{% endfor %}
<h2>Audit trail</h2>
<p>Chain integrity: <strong class="{{ 'ok' if r.audit.chain_valid else 'fail' }}">{{ "valid" if r.audit.chain_valid else "BROKEN" }}</strong> · head <span class="mono">{{ r.audit.chain_head }}</span></p>
<table><tr><th>#</th><th>Time</th><th>Action</th><th>Entity</th><th>Hash</th></tr>
{% for e in r.audit.entries %}<tr><td>{{ e.id }}</td><td>{{ e.ts }}</td><td>{{ e.action }}</td><td class="mono">{{ e.entity }}</td><td class="mono">{{ e.hash[:16] }}…</td></tr>{% endfor %}</table>
<h2>Integrity</h2><p class="mono">manifest sha256: {{ manifest }}</p>
<p class="mu">{{ r.disclaimer }}</p></body></html>""")


def render(report: dict, fmt: str, manifest: str) -> tuple[bytes, str]:
    if fmt == "json":
        return json.dumps({**report, "manifest_sha256": manifest}, indent=2, ensure_ascii=False, default=str).encode(), "application/json"
    html = HTML.render(r=report, manifest=manifest)
    if fmt == "html":
        return html.encode(), "text/html; charset=utf-8"
    import weasyprint  # imported lazily: needs the Pango system libraries present in the container image
    return weasyprint.HTML(string=html).write_pdf(), "application/pdf"


class ReportOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    format: str
    manifest_sha256: str
    created_at: datetime
    size: int
    run_label: str


@router.post("/runs/{run_id}/reports", response_model=ReportOut, status_code=201)
async def create_report(run_id: uuid.UUID, format: Literal["html", "json", "pdf"] = "html", p: Principal = Depends(require("engineer"))):
    report = await build_report(p, run_id)
    manifest = sha256(canonical(report))
    try:
        data, ctype = await asyncio.to_thread(render, report, format, manifest)
    except OSError as e:  # WeasyPrint without system libraries
        raise HTTPException(503, f"PDF rendering is unavailable on this server ({e.__class__.__name__})") from e
    key = evidence_key(p.org_id, run_id, "reports", f"{uuid.uuid4()}.{format}")
    await get_store().put(key, data, ctype)
    ev = EvidenceObject(org_id=p.org_id, run_id=run_id, kind=f"report-{format}", s3_key=key, sha256=sha256(data), size=len(data))
    p.session.add(ev)
    await p.session.flush()
    rep = Report(org_id=p.org_id, run_id=run_id, format=format, evidence_object_id=ev.id, manifest_sha256=manifest)
    p.session.add(rep)
    await p.session.flush()
    await p.session.refresh(rep)
    await audit.record(p.session, p.org_id, p.user_id, "report.create", "report", str(rep.id),
                       after={"run": str(run_id), "format": format, "manifest_sha256": manifest, "file_sha256": ev.sha256})
    return ReportOut(id=rep.id, run_id=run_id, format=format, manifest_sha256=manifest, created_at=rep.created_at, size=ev.size, run_label=str(run_id)[:8])


@router.get("/reports", response_model=list[ReportOut])
async def list_reports(run_id: uuid.UUID | None = None, p: Principal = Depends(principal)):
    q = select(Report, EvidenceObject).join(EvidenceObject, EvidenceObject.id == Report.evidence_object_id).order_by(Report.created_at.desc())
    if run_id:
        q = q.where(Report.run_id == run_id)
    return [ReportOut(id=r.id, run_id=r.run_id, format=r.format, manifest_sha256=r.manifest_sha256, created_at=r.created_at,
                      size=e.size, run_label=str(r.run_id)[:8]) for r, e in (await p.session.execute(q.limit(200))).all()]


@router.get("/reports/{report_id}/download")
async def download_report(report_id: uuid.UUID, p: Principal = Depends(principal)):
    row = (await p.session.execute(select(Report, EvidenceObject).join(EvidenceObject, EvidenceObject.id == Report.evidence_object_id)
                                   .where(Report.id == report_id))).one_or_none()
    if row is None:
        raise HTTPException(404, "Report not found")
    rep, ev = row
    try:
        data = await read_verified(ev.s3_key, ev.sha256)
    except IntegrityError as e:
        raise HTTPException(500, str(e)) from e
    media = {"html": "text/html; charset=utf-8", "json": "application/json", "pdf": "application/pdf"}[rep.format]
    # Served as an attachment with a sandboxing CSP: report HTML embeds untrusted application output.
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="medguard-report-{str(rep.run_id)[:8]}.{rep.format}"',
                                                     "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"})


class EvidenceOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID | None
    kind: str
    sha256: str
    size: int
    created_at: datetime


@router.get("/evidence", response_model=list[EvidenceOut])
async def list_evidence(run_id: uuid.UUID | None = None, limit: int = 200, p: Principal = Depends(require("reviewer"))):
    q = select(EvidenceObject).order_by(EvidenceObject.created_at.desc()).limit(max(1, min(limit, 500)))
    if run_id:
        q = q.where(EvidenceObject.run_id == run_id)
    return [EvidenceOut(id=e.id, run_id=e.run_id, kind=e.kind, sha256=e.sha256, size=e.size, created_at=e.created_at)
            for e in (await p.session.execute(q)).scalars()]


@router.get("/evidence/{evidence_id}/download")
async def download_evidence(evidence_id: uuid.UUID, p: Principal = Depends(require("reviewer"))):
    e = (await p.session.execute(select(EvidenceObject).where(EvidenceObject.id == evidence_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(404, "Evidence not found")
    try:
        data = await read_verified(e.s3_key, e.sha256)
    except IntegrityError as x:
        raise HTTPException(500, str(x)) from x
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{e.kind}-{str(e.id)[:8]}"', "X-Content-Type-Options": "nosniff", "X-Evidence-SHA256": e.sha256})


# ---- settings and retention --------------------------------------------------------------

class SettingsOut(BaseModel):
    org_name: str
    retention_days: int


@router.get("/settings", response_model=SettingsOut)
async def get_settings_(p: Principal = Depends(principal)):
    org = (await p.session.execute(select(Organization))).scalar_one()
    return SettingsOut(org_name=org.name, retention_days=org.retention_days)


class RetentionIn(BaseModel):
    retention_days: int = Field(ge=1, le=3650)


@router.put("/settings/retention", response_model=SettingsOut)
async def set_retention(body: RetentionIn, p: Principal = Depends(require_roles("admin"))):
    org = (await p.session.execute(select(Organization))).scalar_one()
    before = org.retention_days
    org.retention_days = body.retention_days
    await audit.record(p.session, p.org_id, p.user_id, "settings.retention", "organization", str(p.org_id),
                       before={"retention_days": before}, after={"retention_days": body.retention_days})
    return SettingsOut(org_name=org.name, retention_days=org.retention_days)


async def purge_expired(p: Principal) -> dict:
    """Delete stored responses and reports of runs older than the retention period. Run metadata, review and release
    decisions, and the audit trail are kept: they are the record of what was decided and why."""
    org = (await p.session.execute(select(Organization))).scalar_one()
    cutoff = datetime.now(timezone.utc) - timedelta(days=org.retention_days)
    old = (await p.session.execute(select(EvaluationRun.id).where(EvaluationRun.started_at < cutoff))).scalars().all()
    if not old:
        return {"runs": 0, "objects": 0}
    evs = (await p.session.execute(select(EvidenceObject).where(EvidenceObject.run_id.in_(old)))).scalars().all()
    for e in evs:
        await get_store().delete(e.s3_key)
    ev_ids = [e.id for e in evs]
    await p.session.execute(update(RunItem).where(RunItem.run_id.in_(old)).values(response_text=None, response_evidence_id=None))
    await p.session.execute(delete(Report).where(Report.evidence_object_id.in_(ev_ids)))
    await p.session.execute(delete(EvidenceObject).where(EvidenceObject.id.in_(ev_ids)))
    await audit.record(p.session, p.org_id, p.user_id, "retention.purge", "organization", str(p.org_id),
                       after={"runs": len(old), "objects": len(ev_ids), "cutoff": cutoff.isoformat()})
    return {"runs": len(old), "objects": len(ev_ids)}


@router.post("/settings/retention/purge")
async def purge(p: Principal = Depends(require_roles("admin"))):
    return await purge_expired(p)
