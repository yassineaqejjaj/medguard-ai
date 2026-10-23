import csv
import io
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, update

from . import audit
from .models import TestCase, TestSuite
from .schemas import CaseIn, CaseOut, SuiteIn, SuiteOut, Validation
from .security import Principal, principal, require, require_roles

router = APIRouter(prefix="/api/v1")

MAX_IMPORT_BYTES = 2_000_000
CSV_COLUMNS = ["case_key", "category", "input", "reference_context", "expected_behavior", "criteria", "severity",
               "pass_conditions"]


def case_out(c: TestCase) -> CaseOut:
    return CaseOut(id=c.id, suite_id=c.suite_id, case_key=c.case_key, version=c.version, category=c.category,
                   input=c.input, reference_context=c.reference_context, expected_behavior=c.expected_behavior,
                   criteria=c.criteria, severity=c.severity, pass_conditions=c.pass_conditions,
                   validation_status=c.validation_status, position=c.position)


async def _suite(p: Principal, suite_id: uuid.UUID) -> TestSuite:
    s = (await p.session.execute(select(TestSuite).where(TestSuite.id == suite_id))).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Suite not found")
    return s


async def _current_cases(p: Principal, suite_id: uuid.UUID) -> list[TestCase]:
    return list((await p.session.execute(select(TestCase).where(TestCase.suite_id == suite_id, TestCase.is_current)
                                         .order_by(TestCase.position, TestCase.case_key))).scalars())


async def _next_key(p: Principal, suite_id: uuid.UUID) -> str:
    keys = (await p.session.execute(select(TestCase.case_key).where(TestCase.suite_id == suite_id))).scalars().all()
    nums = [int(k.split("-")[-1]) for k in keys if k.startswith("TC-") and k.split("-")[-1].isdigit()]
    return f"TC-{(max(nums) + 1 if nums else 1):04d}"


def _new_case(p: Principal, suite_id: uuid.UUID, key: str, version: int, body: CaseIn, position: int,
              validation: str = "draft") -> TestCase:
    return TestCase(org_id=p.org_id, suite_id=suite_id, case_key=key, version=version, is_current=True,
                    category=body.category, input=body.input, reference_context=body.reference_context,
                    expected_behavior=body.expected_behavior, criteria=body.criteria, severity=body.severity,
                    pass_conditions=body.pass_conditions.model_dump(), validation_status=validation, position=position)


# ---- suites ------------------------------------------------------------------------------

@router.get("/suites", response_model=list[SuiteOut])
async def list_suites(p: Principal = Depends(principal)):
    out = []
    for s in (await p.session.execute(select(TestSuite).order_by(TestSuite.created_at.desc()))).scalars():
        n = (await p.session.execute(select(func.count()).select_from(TestCase)
                                     .where(TestCase.suite_id == s.id, TestCase.is_current))).scalar_one()
        out.append(SuiteOut(id=s.id, name=s.name, description=s.description, case_count=n, created_at=s.created_at))
    return out


@router.post("/suites", response_model=SuiteOut, status_code=201)
async def create_suite(body: SuiteIn, p: Principal = Depends(require("engineer"))):
    if (await p.session.execute(select(TestSuite.id).where(TestSuite.name == body.name))).scalar_one_or_none():
        raise HTTPException(409, "A suite with this name already exists")
    s = TestSuite(org_id=p.org_id, name=body.name, description=body.description)
    p.session.add(s)
    await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "suite.create", "test_suite", str(s.id), after=body.model_dump())
    await p.session.refresh(s)
    return SuiteOut(id=s.id, name=s.name, description=s.description, case_count=0, created_at=s.created_at)


@router.get("/suites/{suite_id}", response_model=list[CaseOut])
async def suite_cases(suite_id: uuid.UUID, p: Principal = Depends(principal)):
    await _suite(p, suite_id)
    return [case_out(c) for c in await _current_cases(p, suite_id)]


# ---- cases -------------------------------------------------------------------------------

@router.post("/suites/{suite_id}/cases", response_model=CaseOut, status_code=201)
async def create_case(suite_id: uuid.UUID, body: CaseIn, p: Principal = Depends(require("engineer"))):
    await _suite(p, suite_id)
    key = await _next_key(p, suite_id)
    pos = len(await _current_cases(p, suite_id))
    c = _new_case(p, suite_id, key, 1, body, pos)
    p.session.add(c)
    await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "case.create", "test_case", str(c.id), after={"key": key, "v": 1})
    return case_out(c)


async def _case(p: Principal, case_id: uuid.UUID) -> TestCase:
    c = (await p.session.execute(select(TestCase).where(TestCase.id == case_id))).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Case not found")
    return c


@router.put("/cases/{case_id}", response_model=CaseOut)
async def edit_case(case_id: uuid.UUID, body: CaseIn, p: Principal = Depends(require("engineer"))):
    """Cases are immutable: an edit writes a new version so past runs still point at what they actually ran.
    Editing resets the human-validation status to draft."""
    old = await _case(p, case_id)
    if not old.is_current:
        raise HTTPException(409, "Only the current version of a case can be edited")
    old.is_current = False
    new = _new_case(p, old.suite_id, old.case_key, old.version + 1, body, old.position)
    p.session.add(new)
    await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "case.edit", "test_case", str(new.id),
                       before={"id": str(old.id), "v": old.version}, after={"v": new.version})
    return case_out(new)


@router.post("/cases/{case_id}/duplicate", response_model=CaseOut, status_code=201)
async def duplicate_case(case_id: uuid.UUID, p: Principal = Depends(require("engineer"))):
    src = await _case(p, case_id)
    body = CaseIn(category=src.category, input=src.input, reference_context=src.reference_context,
                  expected_behavior=src.expected_behavior, criteria=src.criteria, severity=src.severity,
                  pass_conditions=src.pass_conditions)
    key = await _next_key(p, src.suite_id)
    c = _new_case(p, src.suite_id, key, 1, body, len(await _current_cases(p, src.suite_id)))
    p.session.add(c)
    await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "case.duplicate", "test_case", str(c.id), after={"from": src.case_key})
    return case_out(c)


class ValidationIn(BaseModel):
    status: Validation
    justification: str = Field(min_length=1, max_length=2000)


@router.post("/cases/{case_id}/validation", response_model=CaseOut)
async def set_validation(case_id: uuid.UUID, body: ValidationIn, p: Principal = Depends(require_roles("reviewer", "admin"))):
    # Engineers author scenarios but cannot validate their own work.
    c = await _case(p, case_id)
    before = c.validation_status
    c.validation_status = body.status
    await audit.record(p.session, p.org_id, p.user_id, "case.validation", "test_case", str(c.id),
                       before={"status": before}, after={"status": body.status, "justification": body.justification})
    return case_out(c)


class OrderIn(BaseModel):
    case_ids: list[uuid.UUID] = Field(max_length=5000)


@router.put("/suites/{suite_id}/order", response_model=list[CaseOut])
async def reorder(suite_id: uuid.UUID, body: OrderIn, p: Principal = Depends(require("engineer"))):
    await _suite(p, suite_id)
    cases = await _current_cases(p, suite_id)
    if sorted(map(str, body.case_ids)) != sorted(str(c.id) for c in cases):
        raise HTTPException(422, "case_ids must list every current case of the suite exactly once")
    for pos, cid in enumerate(body.case_ids):
        await p.session.execute(update(TestCase).where(TestCase.id == cid).values(position=pos))
    await audit.record(p.session, p.org_id, p.user_id, "suite.reorder", "test_suite", str(suite_id))
    return [case_out(c) for c in await _current_cases(p, suite_id)]


# ---- import / export ---------------------------------------------------------------------

class ImportIn(BaseModel):
    format: Literal["json", "csv"]
    content: str = Field(max_length=MAX_IMPORT_BYTES)


def _parse_rows(fmt: str, content: str) -> list[dict]:
    if fmt == "json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(422, f"Invalid JSON: {e}") from e
        rows = data.get("cases") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise HTTPException(422, 'JSON must be a list of cases or {"cases": [...]}')
        return rows
    reader = csv.DictReader(io.StringIO(content))
    missing = {"category", "input", "severity"} - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(422, f"CSV is missing required columns: {sorted(missing)}")
    rows = []
    for r in reader:
        row = {k: v for k, v in r.items() if k and v not in (None, "")}
        if "criteria" in row:
            row["criteria"] = [c.strip() for c in row["criteria"].split(";") if c.strip()]
        if "pass_conditions" in row:
            try:
                row["pass_conditions"] = json.loads(row["pass_conditions"])
            except json.JSONDecodeError as e:
                raise HTTPException(422, f"Row {len(rows) + 2}: pass_conditions is not valid JSON") from e
        rows.append(row)
    return rows


@router.post("/suites/{suite_id}/import")
async def import_cases(suite_id: uuid.UUID, body: ImportIn, p: Principal = Depends(require("engineer"))):
    """All-or-nothing: any invalid row rejects the whole file, with per-row errors."""
    await _suite(p, suite_id)
    rows = _parse_rows(body.format, body.content)
    if len(rows) > 2000:
        raise HTTPException(422, "At most 2000 cases per import")
    errors, parsed = [], []
    for i, row in enumerate(rows, start=1):
        key = row.pop("case_key", None) if isinstance(row, dict) else None
        try:
            parsed.append((key, CaseIn.model_validate(row)))
        except ValidationError as e:
            errors.append({"row": i, "errors": [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]})
    if errors:
        raise HTTPException(422, detail={"message": "Import rejected: invalid rows", "rows": errors[:50]})
    existing = {c.case_key: c for c in await _current_cases(p, suite_id)}
    created = updated = 0
    pos = len(existing)
    for key, case in parsed:
        if key and key in existing:  # same key => new version of the existing case
            old = existing[key]
            old.is_current = False
            p.session.add(_new_case(p, suite_id, key, old.version + 1, case, old.position))
            updated += 1
        else:
            k = key or await _next_key(p, suite_id)
            await p.session.flush()
            p.session.add(_new_case(p, suite_id, k, 1, case, pos))
            pos += 1
            created += 1
        await p.session.flush()
    await audit.record(p.session, p.org_id, p.user_id, "suite.import", "test_suite", str(suite_id),
                       after={"format": body.format, "created": created, "new_versions": updated})
    return {"created": created, "new_versions": updated}


def _csv_safe(v: str) -> str:
    # Neutralise spreadsheet formula injection when exports are opened in Excel/LibreOffice.
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@router.get("/suites/{suite_id}/export")
async def export_cases(suite_id: uuid.UUID, format: Literal["json", "csv"] = "json", p: Principal = Depends(principal)):
    s = await _suite(p, suite_id)
    cases = await _current_cases(p, suite_id)
    fname = f"{s.name.replace(' ', '_')[:60]}.{format}"
    if format == "json":
        payload = json.dumps({"suite": s.name, "cases": [
            {"case_key": c.case_key, "category": c.category, "input": c.input, "reference_context": c.reference_context,
             "expected_behavior": c.expected_behavior, "criteria": c.criteria, "severity": c.severity,
             "pass_conditions": c.pass_conditions} for c in cases]}, indent=2, ensure_ascii=False)
        media = "application/json"
    else:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(CSV_COLUMNS)
        for c in cases:
            w.writerow([_csv_safe(x) for x in [c.case_key, c.category, c.input, c.reference_context, c.expected_behavior,
                                               ";".join(c.criteria), c.severity,
                                               json.dumps(c.pass_conditions, ensure_ascii=False)]])
        payload, media = buf.getvalue(), "text/csv"
    return Response(payload, media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})
