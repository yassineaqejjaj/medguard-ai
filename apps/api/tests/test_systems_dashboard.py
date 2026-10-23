import pytest
from sqlalchemy import text

from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401  (fixtures)

BODY = {"name": "Clinical Knowledge Assistant", "purpose": "Guideline search", "owner": "AI team",
        "model_name": "demo-model", "version_label": "v1.0.0", "endpoint_url": "http://rag.example.test/ask",
        "auth_type": "bearer", "auth_secret": "super-secret-token"}


async def _hdr(rsa_key, owner_engine, org, role="engineer"):
    return auth(token(rsa_key, await slug_of(owner_engine, org), role))


async def test_create_and_list_system_with_secret_encrypted(client, rsa_key, two_orgs, owner_engine):
    h = await _hdr(rsa_key, owner_engine, two_orgs[0])
    body = {**BODY, "name": "CKA create test"}
    r = await client.post("/api/v1/systems", json=body, headers=h)
    assert r.status_code == 201, r.text
    assert "super-secret-token" not in r.text and r.json()["latest_version"] == "v1.0.0"
    listed = (await client.get("/api/v1/systems", headers=h)).json()
    assert "CKA create test" in [s["name"] for s in listed]

    async with owner_engine.connect() as c:
        enc = (await c.execute(text("SELECT auth_secret_enc FROM ai_system_versions WHERE org_id=:o"),
                               {"o": two_orgs[0]})).scalars().all()
        audit_rows = (await c.execute(text("SELECT after::text FROM audit_log WHERE org_id=:o AND action='system.create'"),
                                      {"o": two_orgs[0]})).scalars().all()
    assert enc and all(e and "super-secret-token" not in e for e in enc)
    assert audit_rows and all("super-secret-token" not in a for a in audit_rows)


async def test_viewer_cannot_create_but_can_list(client, rsa_key, two_orgs, owner_engine):
    h = await _hdr(rsa_key, owner_engine, two_orgs[0], "viewer")
    assert (await client.post("/api/v1/systems", json={**BODY, "name": "x"}, headers=h)).status_code == 403
    assert (await client.get("/api/v1/systems", headers=h)).status_code == 200


async def test_systems_isolated_between_orgs(client, rsa_key, two_orgs, owner_engine):
    ha = await _hdr(rsa_key, owner_engine, two_orgs[0])
    hb = await _hdr(rsa_key, owner_engine, two_orgs[1])
    await client.post("/api/v1/systems", json={**BODY, "name": "Only in A"}, headers=ha)
    names_b = [s["name"] for s in (await client.get("/api/v1/systems", headers=hb)).json()]
    assert "Only in A" not in names_b
    # Same name in another org is allowed (uniqueness is per tenant).
    assert (await client.post("/api/v1/systems", json={**BODY, "name": "Only in A"}, headers=hb)).status_code == 201


@pytest.mark.parametrize("patch,code", [
    ({"endpoint_url": "ftp://x.test"}, 422),
    ({"endpoint_url": "http://user:pw@x.test/"}, 422),
    ({"endpoint_url": "not a url"}, 422),
    ({"name": ""}, 422),
    ({"auth_secret": None}, 422),
])
async def test_invalid_input_rejected(client, rsa_key, two_orgs, owner_engine, patch, code):
    h = await _hdr(rsa_key, owner_engine, two_orgs[0])
    r = await client.post("/api/v1/systems", json={**BODY, "name": "bad", **patch}, headers=h)
    assert r.status_code == code


async def test_duplicate_name_conflict(client, rsa_key, two_orgs, owner_engine):
    h = await _hdr(rsa_key, owner_engine, two_orgs[0])
    body = {**BODY, "name": "Dup test"}
    assert (await client.post("/api/v1/systems", json=body, headers=h)).status_code == 201
    assert (await client.post("/api/v1/systems", json=body, headers=h)).status_code == 409


async def test_dashboard_summary_empty_then_computed(client, rsa_key, two_orgs, owner_engine):
    org = two_orgs[1]
    h = await _hdr(rsa_key, owner_engine, org)
    await client.post("/api/v1/systems", json={**BODY, "name": "Summary sys"}, headers=h)
    s = (await client.get("/api/v1/dashboard/summary", headers=h)).json()
    assert s["systems"] == 1 and s["runs"] == 0
    assert s["pass_rate"] is None  # no results yet: never a fabricated number
    assert s["critical_failures"] == 0 and s["pending_reviews"] == 0
    assert s["never_evaluated"] == ["Summary sys"]

    async with owner_engine.begin() as c:  # seed one run: 2 passed, 1 critical failure (needs review)
        ver = (await c.execute(text("SELECT id FROM ai_system_versions WHERE org_id=:o"), {"o": org})).scalar_one()
        suite = (await c.execute(text(
            "INSERT INTO test_suites (id,org_id,name,description) VALUES (gen_random_uuid(),:o,'s','') RETURNING id"),
            {"o": org})).scalar_one()
        run = (await c.execute(text(
            "INSERT INTO evaluation_runs (id,org_id,system_version_id,suite_id,status,params,judge_prompt_versions) "
            "VALUES (gen_random_uuid(),:o,:v,:s,'completed','{}','{}') RETURNING id"), {"o": org, "v": ver, "s": suite})).scalar_one()
        for i, (sev, st, rev) in enumerate([("low", "passed", False), ("high", "passed", False), ("critical", "failed", True)]):
            case = (await c.execute(text(
                "INSERT INTO test_cases (id,org_id,suite_id,case_key,version,is_current,category,input,reference_context,"
                "expected_behavior,criteria,severity,pass_conditions,validation_status,position) VALUES "
                "(gen_random_uuid(),:o,:s,:k,1,true,'c','q','','','[]',:sev,'{}','draft',0) RETURNING id"),
                {"o": org, "s": suite, "k": f"TC-{i}", "sev": sev})).scalar_one()
            await c.execute(text(
                "INSERT INTO run_items (id,org_id,run_id,test_case_id,status,needs_review,review_reasons) "
                "VALUES (gen_random_uuid(),:o,:r,:c,:st,:rev,'[]')"), {"o": org, "r": run, "c": case, "st": st, "rev": rev})
    s = (await client.get("/api/v1/dashboard/summary", headers=h)).json()
    assert s["runs"] == 1 and s["runs_last_30d"] == 1
    assert s["pass_rate"] == pytest.approx(2 / 3) and s["tests_evaluated"] == 3
    assert s["critical_failures"] == 1 and s["pending_reviews"] == 1
    assert s["never_evaluated"] == []


async def test_add_version_and_list(client, rsa_key, two_orgs, owner_engine):
    h = await _hdr(rsa_key, owner_engine, two_orgs[0])
    sid = (await client.post("/api/v1/systems", json={**BODY, "name": "Versioned"}, headers=h)).json()["id"]
    v = {"version_label": "v2.0.0", "endpoint_url": "http://rag.example.test/ask2", "auth_type": "none"}
    r = await client.post(f"/api/v1/systems/{sid}/versions", json=v, headers=h)
    assert r.status_code == 201 and r.json()["version_label"] == "v2.0.0" and r.json()["run_count"] == 0
    assert (await client.post(f"/api/v1/systems/{sid}/versions", json=v, headers=h)).status_code == 409
    labels = [x["version_label"] for x in (await client.get(f"/api/v1/versions?system_id={sid}", headers=h)).json()]
    assert labels == ["v1.0.0", "v2.0.0"]
    assert "super-secret-token" not in (await client.get("/api/v1/versions", headers=h)).text
    # latest version of the system is now v2.0.0
    systems = (await client.get("/api/v1/systems", headers=h)).json()
    assert next(s for s in systems if s["id"] == sid)["latest_version"] == "v2.0.0"
    # bad input, wrong tenant, wrong role
    assert (await client.post(f"/api/v1/systems/{sid}/versions", json={**v, "version_label": "v3", "endpoint_url": "ftp://x"}, headers=h)).status_code == 422
    hb = await _hdr(rsa_key, owner_engine, two_orgs[1])
    assert (await client.post(f"/api/v1/systems/{sid}/versions", json={**v, "version_label": "v9"}, headers=hb)).status_code == 404
    hv = await _hdr(rsa_key, owner_engine, two_orgs[0], "viewer")
    assert (await client.post(f"/api/v1/systems/{sid}/versions", json={**v, "version_label": "v9"}, headers=hv)).status_code == 403
