"""Load the synthetic demo into an organisation (idempotent). Runs as the schema owner.

Usage: python -m medguard_api.seed_demo demo-org http://demo-assistant-v1:9000/ask http://demo-assistant-v2:9000/ask
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from .models import AISystem, AISystemVersion, TestCase, TestSuite
from .schemas import CaseIn

_here = Path(__file__).resolve()
SUITE_PATHS = [Path("/app/suites/medical_rag_demo_v1.json")]
if len(_here.parents) > 3:  # inside the monorepo checkout
    SUITE_PATHS.append(_here.parents[3] / "evaluation/test_suites/medical_rag_demo_v1.json")


async def main(slug: str, v1_url: str, v2_url: str) -> None:
    suite_file = next(p for p in SUITE_PATHS if p.exists())
    data = json.loads(suite_file.read_text())
    engine = create_async_engine(os.environ["MEDGUARD_MIGRATION_URL"])
    async with AsyncSession(engine) as s, s.begin():
        org_id = (await s.execute(text("SELECT id FROM organizations WHERE slug=:s"), {"s": slug})).scalar_one()
        await s.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_id)})
        name = "Demo Clinical Assistant"
        if not (await s.execute(select(AISystem.id).where(AISystem.name == name))).scalar_one_or_none():
            sysm = AISystem(org_id=org_id, name=name, description="Fictional RAG assistant (synthetic corpus)",
                            purpose="Guideline and administrative documentation search", usage_context="Demo",
                            owner="MedGuard demo", model_name="demo-stub", doc_sources=["DOC-HYP-01", "DOC-REN-02"])
            s.add(sysm)
            await s.flush()
            for label, url in (("v1.0.0", v1_url), ("v1.1.0", v2_url)):  # v1.1.0 ships deliberate regressions
                s.add(AISystemVersion(org_id=org_id, system_id=sysm.id, version_label=label, endpoint_url=url,
                                      auth_type="none", request_template={}, response_mapping={}, timeout_s=30.0))
        if not (await s.execute(select(TestSuite.id).where(TestSuite.name == data["suite"]))).scalar_one_or_none():
            suite = TestSuite(org_id=org_id, name=data["suite"], description="20 synthetic scenarios, no real patient data")
            s.add(suite)
            await s.flush()
            for i, raw in enumerate(data["cases"], start=1):
                c = CaseIn.model_validate(raw)
                s.add(TestCase(org_id=org_id, suite_id=suite.id, case_key=f"TC-{i:04d}", version=1, is_current=True,
                               category=c.category, input=c.input, reference_context=c.reference_context,
                               expected_behavior=c.expected_behavior, criteria=c.criteria, severity=c.severity,
                               pass_conditions=c.pass_conditions.model_dump(), validation_status="draft", position=i - 1))
    await engine.dispose()
    print("demo data loaded")


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:4]))
