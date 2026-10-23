import asyncio
import json
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from ..config import get_settings
from ..crypto import decrypt_secret
from ..db import sessionmaker, set_tenant
from ..models import AISystemVersion, CriterionResult, EvaluationRun, EvidenceObject, RunItem, TestCase
from ..schemas import PassConditions
from ..storage import evidence_key, get_store, sha256
from .adapters import call_application
from .deterministic import run_checks
from .judge import INFERENCE_PARAMS, JUDGE_PROMPT_VERSION, JudgeConfig, judge_criterion
from .scoring import decide


def judge_config() -> JudgeConfig | None:
    s = get_settings()
    return JudgeConfig(s.judge_url, s.judge_model, s.judge_api_key) if s.judge_url else None


async def _tenant(org_id: uuid.UUID):
    session = sessionmaker()()
    await session.begin()
    await set_tenant(session, org_id)
    return session


async def _process_item(org_id: uuid.UUID, item_id: uuid.UUID, version_id: uuid.UUID, cfg: JudgeConfig | None,
                        sem: asyncio.Semaphore, judge_client: httpx.AsyncClient | None) -> None:
    async with sem:
        s = await _tenant(org_id)
        try:
            item = (await s.execute(select(RunItem).where(RunItem.id == item_id))).scalar_one()
            case = (await s.execute(select(TestCase).where(TestCase.id == item.test_case_id))).scalar_one()
            ver = (await s.execute(select(AISystemVersion).where(AISystemVersion.id == version_id))).scalar_one()
            secret = decrypt_secret(ver.auth_secret_enc) if ver.auth_secret_enc else None
            settings = get_settings()
            res = await call_application(
                url=ver.endpoint_url, question=case.input, template=ver.request_template or None,
                mapping=ver.response_mapping or None, auth_type=ver.auth_type, auth_secret=secret,
                auth_header=ver.auth_header_name, timeout_s=ver.timeout_s, allow_private=settings.allow_private_targets)
            pc = PassConditions.model_validate(case.pass_conditions)
            results = run_checks(res, pc)
            if res.ok and case.criteria:
                for crit in case.criteria:
                    results.append(await judge_criterion(
                        cfg, crit, question=case.input, reference=case.reference_context,
                        expected=case.expected_behavior, answer=res.answer or res.raw_text, client=judge_client))
            status, needs_review, reasons = decide(case.severity, results)
            payload = json.dumps({"case_key": case.case_key, "case_version": case.version, "question": case.input,
                                  "status_code": res.status_code, "latency_ms": res.latency_ms, "error": res.error,
                                  "response": res.raw_text}, ensure_ascii=False).encode()
            key = evidence_key(org_id, item.run_id, "responses", f"{item.id}.json")
            await get_store().put(key, payload, "application/json")  # failure here marks the item as an engine error
            ev = EvidenceObject(org_id=org_id, run_id=item.run_id, kind="response", s3_key=key, sha256=sha256(payload), size=len(payload))
            s.add(ev)
            await s.flush()
            item.response_evidence_id = ev.id
            item.response_text = res.raw_text[:200_000]
            item.latency_ms = res.latency_ms
            item.status, item.needs_review, item.review_reasons = status, needs_review, reasons
            for r in results:
                s.add(CriterionResult(org_id=org_id, run_item_id=item.id, **r))
            await s.commit()
        except Exception:
            await s.rollback()
            # Record the failure on the item rather than losing it, using a fresh transaction.
            s2 = await _tenant(org_id)
            item = (await s2.execute(select(RunItem).where(RunItem.id == item_id))).scalar_one()
            item.status, item.needs_review, item.review_reasons = "error", True, ["engine_error"]
            await s2.commit()
            await s2.close()
        finally:
            await s.close()


async def execute_run(org_id: uuid.UUID, run_id: uuid.UUID) -> None:
    cfg = judge_config()
    run = None
    for _ in range(15):  # the API enqueues before its transaction commits; wait for the run to become visible
        s = await _tenant(org_id)
        run = (await s.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
        if run is not None:
            break
        await s.close()
        await asyncio.sleep(1)
    if run is None:
        raise RuntimeError(f"run {run_id} not found")
    run.status = "running"
    run.params = {"inference": INFERENCE_PARAMS, "pass_threshold": 0.7, "adapter": "http-json", "judge_enabled": cfg is not None}
    run.judge_model = cfg.model if cfg else None
    run.judge_model_digest = get_settings().judge_model_digest if cfg else None
    run.judge_prompt_versions = {"judge": JUDGE_PROMPT_VERSION} if cfg else {}
    version_id = run.system_version_id
    item_ids = list((await s.execute(select(RunItem.id).where(RunItem.run_id == run_id, RunItem.status == "pending"))).scalars())
    await s.commit()
    await s.close()

    sem = asyncio.Semaphore(get_settings().run_concurrency)
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_s if cfg else 10) as jc:
            await asyncio.gather(*[_process_item(org_id, i, version_id, cfg, sem, jc) for i in item_ids])
        final = "completed"
    except Exception:
        final = "failed"
    s = await _tenant(org_id)
    run = (await s.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one()
    run.status, run.finished_at = final, datetime.now(timezone.utc)
    await s.commit()
    await s.close()
