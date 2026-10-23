import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from medguard_api.reports import canonical
from medguard_api.storage import MemoryStore
from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401
from tests.test_engine_e2e import (allow_private, no_enqueue, run_and_wait, servers, setup, SUITE)  # noqa: F401


async def hdr(rsa_key, owner_engine, org, role, sub=None):
    return auth(token(rsa_key, await slug_of(owner_engine, org), role, sub=sub))


@pytest.fixture
def no_judge(monkeypatch):
    from medguard_api import config
    monkeypatch.delenv("MEDGUARD_JUDGE_URL", raising=False)
    config.get_settings.cache_clear()


async def one_run(client, h, servers, org, which="v2"):
    suite_id, vers = await setup(client, h, servers, org)
    run, rid = await run_and_wait(client, h, org, vers[which], suite_id)
    return suite_id, vers, rid


async def test_responses_are_stored_as_hashed_evidence_and_json_report_is_verifiable(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers, rid = await one_run(client, eng, servers, org)
    ev = (await client.get(f"/api/v1/evidence?run_id={rid}", headers=eng)).json()
    assert len(ev) == 20 and all(e["kind"] == "response" and len(e["sha256"]) == 64 for e in ev)
    blob = await client.get(f"/api/v1/evidence/{ev[0]['id']}/download", headers=eng)
    assert blob.status_code == 200 and hashlib.sha256(blob.content).hexdigest() == ev[0]["sha256"]
    assert blob.headers["x-evidence-sha256"] == ev[0]["sha256"]

    rep = (await client.post(f"/api/v1/runs/{rid}/reports?format=json", headers=eng)).json()
    data = (await client.get(f"/api/v1/reports/{rep['id']}/download", headers=eng)).json()
    manifest = data.pop("manifest_sha256")
    assert manifest == rep["manifest_sha256"] == hashlib.sha256(canonical(data)).hexdigest()
    # everything needed to trace the campaign is in the report
    assert data["run"]["id"] == rid and data["run"]["application"] == "Demo assistant" and data["run"]["version"] == "v2"
    assert data["run"]["parameters"]["inference"]["seed"] == 42 and data["summary"]["critical_failures"] == 3
    sc = data["scenarios"][0]
    assert sc["case_version"] == 1 and sc["response_evidence"]["sha256"] and sc["criteria"]
    assert data["audit"]["chain_valid"] is True and any(e["action"] == "run.create" for e in data["audit"]["entries"])


async def test_html_report_escapes_untrusted_content_and_is_served_sandboxed(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers = await setup(client, eng, servers, org)
    evil = {"category": "XSS", "input": "<script>alert('x')</script> hello", "severity": "low", "pass_conditions": {"must_contain": ["<img src=x onerror=1>"]}}
    s2 = (await client.post("/api/v1/suites", json={"name": "evil"}, headers=eng)).json()["id"]
    await client.post(f"/api/v1/suites/{s2}/cases", json=evil, headers=eng)
    run, rid = await run_and_wait(client, eng, org, vers["v1"], s2)
    rep = (await client.post(f"/api/v1/runs/{rid}/reports?format=html", headers=eng)).json()
    r = await client.get(f"/api/v1/reports/{rep['id']}/download", headers=eng)
    assert "<script>alert" not in r.text and "&lt;script&gt;alert" in r.text
    assert "onerror=1>" not in r.text.replace("&lt;img src=x onerror=1&gt;", "")
    assert "sandbox" in r.headers["content-security-policy"] and r.headers["content-disposition"].startswith("attachment")


async def test_pdf_report(client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    try:
        import weasyprint
        weasyprint.HTML(string="<p>x</p>").write_pdf()
    except OSError:
        pytest.skip("WeasyPrint system libraries (Pango) are not installed on this host; verified in the container image")
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers, rid = await one_run(client, eng, servers, org)
    rep = (await client.post(f"/api/v1/runs/{rid}/reports?format=pdf", headers=eng)).json()
    pdf = await client.get(f"/api/v1/reports/{rep['id']}/download", headers=eng)
    assert pdf.content.startswith(b"%PDF")


async def test_tampered_evidence_is_detected_on_download(client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers, rid = await one_run(client, eng, servers, org, "v1")
    ev = (await client.get(f"/api/v1/evidence?run_id={rid}", headers=eng)).json()[0]
    async with owner_engine.connect() as c:
        key = (await c.execute(text("SELECT s3_key FROM evidence_objects WHERE id=:i"), {"i": ev["id"]})).scalar_one()
    MemoryStore.objects[key] = b'{"response": "silently edited"}'
    r = await client.get(f"/api/v1/evidence/{ev['id']}/download", headers=eng)
    assert r.status_code == 500 and "no longer matches" in r.text


async def test_roles_and_tenancy_for_reports(client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers, rid = await one_run(client, eng, servers, org, "v1")
    viewer = await hdr(rsa_key, owner_engine, org, "viewer")
    other = await hdr(rsa_key, owner_engine, two_orgs[1], "admin")
    assert (await client.post(f"/api/v1/runs/{rid}/reports?format=json", headers=viewer)).status_code == 403
    assert (await client.get(f"/api/v1/evidence?run_id={rid}", headers=viewer)).status_code == 403
    assert (await client.post(f"/api/v1/runs/{rid}/reports?format=json", headers=other)).status_code == 404
    rep = (await client.post(f"/api/v1/runs/{rid}/reports?format=json", headers=eng)).json()
    assert (await client.get(f"/api/v1/reports/{rep['id']}/download", headers=other)).status_code == 404
    assert (await client.get("/api/v1/evidence", headers=other)).json() == []
    assert (await client.post(f"/api/v1/runs/{rid}/reports?format=exe", headers=eng)).status_code == 422


async def test_retention_purge_removes_responses_but_keeps_decisions_and_audit(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    adm = await hdr(rsa_key, owner_engine, org, "admin")
    suite_id, vers, rid = await one_run(client, eng, servers, org, "v2")
    await client.post(f"/api/v1/runs/{rid}/gate", json={}, headers=eng)
    await client.post(f"/api/v1/runs/{rid}/reports?format=json", headers=eng)
    assert (await client.put("/api/v1/settings/retention", json={"retention_days": 0}, headers=adm)).status_code == 422
    assert (await client.put("/api/v1/settings/retention", json={"retention_days": 30}, headers=eng)).status_code == 403
    assert (await client.put("/api/v1/settings/retention", json={"retention_days": 30}, headers=adm)).json()["retention_days"] == 30
    assert (await client.post("/api/v1/settings/retention/purge", headers=adm)).json() == {"runs": 0, "objects": 0}  # nothing is old yet

    async with owner_engine.begin() as c:
        await c.execute(text("UPDATE evaluation_runs SET started_at=:t WHERE id=:i"), {"t": datetime.now(timezone.utc) - timedelta(days=90), "i": rid})
    out = (await client.post("/api/v1/settings/retention/purge", headers=adm)).json()
    assert out["runs"] == 1 and out["objects"] == 21  # 20 responses + 1 report
    assert (await client.get(f"/api/v1/evidence?run_id={rid}", headers=eng)).json() == []
    items = (await client.get(f"/api/v1/runs/{rid}/items", headers=eng)).json()
    assert all(i["response_text"] is None for i in items) and items[0]["criteria"]  # metadata and verdicts survive
    assert (await client.get(f"/api/v1/runs/{rid}/gate", headers=eng)).json()["status"] == "FAIL"
    audit = (await client.get("/api/v1/audit?action=retention", headers=adm)).json()
    assert audit["chain_valid"] and audit["entries"][0]["action"] == "retention.purge"


async def test_audit_listing_filters_and_chain(client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    adm = await hdr(rsa_key, owner_engine, org, "admin")
    await one_run(client, eng, servers, org, "v1")
    a = (await client.get("/api/v1/audit?action=run.", headers=adm)).json()
    assert a["chain_valid"] and {e["action"] for e in a["entries"]} == {"run.create"}
    assert a["entries"][0]["actor"]
    first = (await client.get("/api/v1/audit?limit=2", headers=adm)).json()["entries"]
    older = (await client.get(f"/api/v1/audit?limit=2&before_id={first[-1]['id']}", headers=adm)).json()["entries"]
    assert all(e["id"] < first[-1]["id"] for e in older)
    assert (await client.get("/api/v1/audit", headers=eng)).status_code == 403
