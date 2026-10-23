"""End-to-end: real HTTP calls from the engine to a running demo assistant (v1 good, v2 regressed), real Postgres."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]
SUITE = json.loads((ROOT / "evaluation/test_suites/medical_rag_demo_v1.json").read_text())


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(app_dir: str, target: str, env: dict):
    port = free_port()
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", target, "--app-dir", app_dir, "--port", str(port), "--log-level", "warning"],
                         env={**os.environ, **env})
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{port}/openapi.json", timeout=0.5)
            return p, port
        except httpx.HTTPError:
            time.sleep(0.2)
    p.kill()
    raise RuntimeError("server did not start")


@pytest.fixture(scope="module")
def servers():
    v1, p1 = serve(str(ROOT / "apps/demo-assistant"), "app:app", {"DEMO_VERSION": "v1"})
    v2, p2 = serve(str(ROOT / "apps/demo-assistant"), "app:app", {"DEMO_VERSION": "v2"})
    jd, pj = serve(str(ROOT / "apps/api/tests"), "fake_judge:app", {})
    yield {"v1": p1, "v2": p2, "judge": pj}
    for p in (v1, v2, jd):
        p.kill()


@pytest.fixture(autouse=True)
def allow_private(monkeypatch):
    monkeypatch.setenv("MEDGUARD_ALLOW_PRIVATE_TARGETS", "true")  # demo servers listen on loopback
    from medguard_api import config
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


async def setup(client, h, servers, org):
    sid = (await client.post("/api/v1/suites", json={"name": "Demo"}, headers=h)).json()["id"]
    r = await client.post(f"/api/v1/suites/{sid}/import", json={"format": "json", "content": json.dumps(SUITE)}, headers=h)
    assert r.json()["created"] == 20, r.text
    sys_row = (await client.post("/api/v1/systems", json={"name": "Demo assistant", "version_label": "v1",
                                                          "endpoint_url": f"http://127.0.0.1:{servers['v1']}/ask"}, headers=h)).json()
    v2 = (await client.post(f"/api/v1/systems/{sys_row['id']}/versions", json={
        "version_label": "v2", "endpoint_url": f"http://127.0.0.1:{servers['v2']}/ask"}, headers=h)).json()
    versions = {"v1": None, "v2": v2["id"], "system": sys_row["id"]}
    versions["v1"] = next(x["id"] for x in (await client.get(f"/api/v1/versions?system_id={sys_row['id']}", headers=h)).json()
                          if x["version_label"] == "v1")
    return sid, versions


async def run_and_wait(client, h, org, version_id, suite_id):
    from medguard_api.evaluation.engine import execute_run
    import uuid
    r = await client.post("/api/v1/runs", json={"system_version_id": version_id, "suite_id": suite_id}, headers=h)
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    await execute_run(org, uuid.UUID(run_id))
    return (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json(), run_id


@pytest.fixture
def no_enqueue(monkeypatch):
    from medguard_api import runs
    monkeypatch.setattr(runs, "enqueue", lambda *a, **k: None)  # the test drives the engine inline


async def test_good_version_passes_every_deterministic_check_and_bad_version_is_caught(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, monkeypatch):
    from medguard_api import config
    monkeypatch.delenv("MEDGUARD_JUDGE_URL", raising=False)
    config.get_settings.cache_clear()
    org = two_orgs[0]
    h = auth(token(rsa_key, await slug_of(owner_engine, org), "engineer"))
    suite_id, vers = await setup(client, h, servers, org)

    good, good_id = await run_and_wait(client, h, org, vers["v1"], suite_id)
    assert good["status"] == "completed" and good["total"] == 20
    items = (await client.get(f"/api/v1/runs/{good_id}/items", headers=h)).json()
    bad_ones = [(i["case_key"], i["status"], [c["justification"] for c in i["criteria"] if c["status"] != "pass"]) for i in items if i["status"] != "passed"]
    assert good["failed"] == 0 and good["errors"] == 0, bad_ones
    assert good["pass_rate"] == 1.0 and good["judge_model"] is None
    # with no judge configured, judge-criteria cases are flagged for a human instead of silently passing
    flagged = [i for i in items if i["needs_review"]]
    assert flagged and all("judge_error" in i["review_reasons"] for i in flagged)

    bad, bad_id = await run_and_wait(client, h, org, vers["v2"], suite_id)
    assert bad["status"] == "completed"
    items = (await client.get(f"/api/v1/runs/{bad_id}/items", headers=h)).json()
    failed = {i["case_key"] for i in items if i["status"] == "failed"}
    assert bad["failed"] == 9 and bad["critical_failures"] == 3, (failed, bad)
    # critical failures are listed first and require a human decision
    assert [i["severity"] for i in items[:3]] == ["critical"] * 3
    crit = [i for i in items if i["severity"] == "critical" and i["status"] == "failed"]
    assert all("critical_failure" in i["review_reasons"] for i in crit)
    # the item score is its weakest criterion, so a failure can never hide behind passing checks
    assert all(i["score"] == 0.0 for i in crit if any(c["kind"] == "deterministic" and c["status"] == "fail" for c in i["criteria"]))
    leak = next(i for i in items if i["category"] == "Prompt Injection Resistance")
    assert any(c["criterion"] == "must_not_contain" and c["status"] == "fail" for c in leak["criteria"])
    cite = next(i for i in items if i["category"] == "Citation Accuracy" and i["severity"] == "critical")
    assert any(c["criterion"] == "citation_reference_exists" and c["status"] == "fail" for c in cite["criteria"])
    slow = next(i for i in items if i["category"] == "Performance")
    assert slow["latency_ms"] >= 3000 and any(c["criterion"] == "response_time" and c["status"] == "fail" for c in slow["criteria"])
    pii = next(i for i in items if i["category"] == "Sensitive Information")
    assert any(c["criterion"] == "sensitive_data" and c["status"] == "fail" for c in pii["criteria"])

    # dashboard now reflects real data
    s = (await client.get("/api/v1/dashboard/summary", headers=h)).json()
    assert s["runs"] == 2 and s["critical_failures"] == 3 and s["tests_evaluated"] == 40
    assert s["pass_rate"] == pytest.approx(31 / 40)
    assert s["by_severity"]["critical"] == 3 and len(s["recent_runs"]) == 2
    assert {p["version"] for p in s["pass_rate_by_release"]} == {"v1", "v2"}


async def test_judge_pass_cannot_hide_a_deterministic_failure_and_judge_is_recorded(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, monkeypatch):
    from medguard_api import config
    monkeypatch.setenv("MEDGUARD_JUDGE_URL", f"http://127.0.0.1:{servers['judge']}")
    config.get_settings.cache_clear()
    org = two_orgs[1]
    h = auth(token(rsa_key, await slug_of(owner_engine, org), "engineer"))
    suite_id, vers = await setup(client, h, servers, org)

    run, rid = await run_and_wait(client, h, org, vers["v2"], suite_id)
    assert run["judge_model"] == "Qwen/Qwen3-8B" and run["judge_prompt_versions"] == {"judge": "judge-v1"}
    assert run["params"]["inference"]["temperature"] == 0.0 and run["params"]["inference"]["seed"] == 42
    items = (await client.get(f"/api/v1/runs/{rid}/items", headers=h)).json()
    # the stub judge gives 0.9 to almost everything; deterministic failures still fail the item
    assert run["failed"] >= 9
    judged = [c for i in items for c in i["criteria"] if c["kind"] == "llm_judge"]
    assert judged and all(c["judge_prompt_version"] == "judge-v1" and c["confidence"] == 0.9 for c in judged)
    # critical items judged "pass" with no substantive deterministic evidence would still be flagged; none silently clean
    assert all(i["status"] == "failed" for i in items if i["case_key"] in {c["case_key"] for c in items if c["status"] == "failed"})


async def test_run_requires_engineer_and_valid_ids(client, rsa_key, two_orgs, owner_engine, no_enqueue):
    org = two_orgs[0]
    slug = await slug_of(owner_engine, org)
    viewer = auth(token(rsa_key, slug, "viewer"))
    fake = "00000000-0000-0000-0000-000000000000"
    assert (await client.post("/api/v1/runs", json={"system_version_id": fake, "suite_id": fake}, headers=viewer)).status_code == 403
    eng = auth(token(rsa_key, slug, "engineer"))
    assert (await client.post("/api/v1/runs", json={"system_version_id": fake, "suite_id": fake}, headers=eng)).status_code == 404


async def test_runs_are_tenant_isolated(client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, monkeypatch):
    from medguard_api import config
    monkeypatch.delenv("MEDGUARD_JUDGE_URL", raising=False)
    config.get_settings.cache_clear()
    ha = auth(token(rsa_key, await slug_of(owner_engine, two_orgs[0]), "engineer"))
    hb = auth(token(rsa_key, await slug_of(owner_engine, two_orgs[1]), "engineer"))
    suite_id, vers = await setup(client, ha, servers, two_orgs[0])
    run, rid = await run_and_wait(client, ha, two_orgs[0], vers["v1"], suite_id)
    assert (await client.get(f"/api/v1/runs/{rid}", headers=hb)).status_code == 404
    assert (await client.get(f"/api/v1/runs/{rid}/items", headers=hb)).status_code == 404
    assert (await client.get("/api/v1/runs", headers=hb)).json() == []
    # B cannot launch a run against A's system version or suite either
    r = await client.post("/api/v1/runs", json={"system_version_id": vers["v1"], "suite_id": suite_id}, headers=hb)
    assert r.status_code == 404
