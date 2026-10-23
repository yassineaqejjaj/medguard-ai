import uuid

from sqlalchemy import text

from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401


async def seed_items(owner_engine, org):
    """One run with: a critical failure flagged for review, a judge-flagged pass, and an unflagged pass."""
    async with owner_engine.begin() as c:
        sysid = (await c.execute(text(
            "INSERT INTO ai_systems (id,org_id,name,description,purpose,usage_context,owner,doc_sources) "
            "VALUES (gen_random_uuid(),:o,:n,'','','','','[]') RETURNING id"), {"o": org, "n": f"s-{uuid.uuid4().hex[:6]}"})).scalar_one()
        ver = (await c.execute(text(
            "INSERT INTO ai_system_versions (id,org_id,system_id,version_label,endpoint_url,auth_type,request_template,response_mapping,timeout_s) "
            "VALUES (gen_random_uuid(),:o,:s,'v1','http://x.test','none','{}','{}',30) RETURNING id"), {"o": org, "s": sysid})).scalar_one()
        suite = (await c.execute(text("INSERT INTO test_suites (id,org_id,name,description) VALUES (gen_random_uuid(),:o,'s','') RETURNING id"), {"o": org})).scalar_one()
        run = (await c.execute(text(
            "INSERT INTO evaluation_runs (id,org_id,system_version_id,suite_id,status,params,judge_prompt_versions) "
            "VALUES (gen_random_uuid(),:o,:v,:s,'completed','{}','{}') RETURNING id"), {"o": org, "v": ver, "s": suite})).scalar_one()
        ids = []
        for i, (sev, st, rev) in enumerate([("critical", "failed", True), ("high", "passed", True), ("low", "passed", False)]):
            case = (await c.execute(text(
                "INSERT INTO test_cases (id,org_id,suite_id,case_key,version,is_current,category,input,reference_context,expected_behavior,"
                "criteria,severity,pass_conditions,validation_status,position) VALUES (gen_random_uuid(),:o,:s,:k,1,true,'c','q','','','[]',:sev,'{}','draft',0) RETURNING id"),
                {"o": org, "s": suite, "k": f"TC-{i}", "sev": sev})).scalar_one()
            ids.append((await c.execute(text(
                "INSERT INTO run_items (id,org_id,run_id,test_case_id,status,needs_review,review_reasons) "
                "VALUES (gen_random_uuid(),:o,:r,:c,:st,:rev,'[\"critical_failure\"]') RETURNING id"),
                {"o": org, "r": run, "c": case, "st": st, "rev": rev})).scalar_one())
    return [str(i) for i in ids]  # [critical flagged, high flagged, low unflagged]


async def hdr(rsa_key, owner_engine, org, role, sub=None):
    return auth(token(rsa_key, await slug_of(owner_engine, org), role, sub=sub))


REJECT = {"decision": "reject", "error_severity": "critical", "justification": "Cites a section that does not exist.",
          "annotations": [{"kind": "citation_error", "note": "section 9.9 is invented", "quote": "§9.9"}]}
ACCEPT = {"decision": "accept", "justification": "The wording is acceptable on reading the source."}


async def test_only_reviewers_and_admins_can_review(client, rsa_key, two_orgs, owner_engine):
    crit, _, _ = await seed_items(owner_engine, two_orgs[0])
    for role in ("viewer", "engineer"):
        h = await hdr(rsa_key, owner_engine, two_orgs[0], role)
        assert (await client.post(f"/api/v1/run-items/{crit}/reviews", json=REJECT, headers=h)).status_code == 403
    h = await hdr(rsa_key, owner_engine, two_orgs[0], "reviewer")
    r = await client.post(f"/api/v1/run-items/{crit}/reviews", json=REJECT, headers=h)
    assert r.status_code == 201 and r.json()["status"] == "agreed" and r.json()["final_decision"] == "reject"
    assert r.json()["reviews"][0]["reviewer"]  # identity is recorded


async def test_input_validation(client, rsa_key, two_orgs, owner_engine):
    crit, _, plain = await seed_items(owner_engine, two_orgs[0])
    h = await hdr(rsa_key, owner_engine, two_orgs[0], "reviewer")
    url = f"/api/v1/run-items/{crit}/reviews"
    assert (await client.post(url, json={**REJECT, "error_severity": None}, headers=h)).status_code == 422
    assert (await client.post(url, json={**ACCEPT, "error_severity": "low"}, headers=h)).status_code == 422
    assert (await client.post(url, json={**REJECT, "justification": "no"}, headers=h)).status_code == 422
    assert (await client.post(url, json={**REJECT, "justification": " " * 12}, headers=h)).status_code == 422
    bad = {**REJECT, "annotations": [{"kind": "vibes", "note": "x"}]}
    assert (await client.post(url, json=bad, headers=h)).status_code == 422
    # an unflagged result cannot be reviewed
    assert (await client.post(f"/api/v1/run-items/{plain}/reviews", json=ACCEPT, headers=h)).status_code == 409


async def test_critical_failure_stays_pending_until_a_human_decides(client, rsa_key, two_orgs, owner_engine):
    crit, high, _ = await seed_items(owner_engine, two_orgs[0])
    h = await hdr(rsa_key, owner_engine, two_orgs[0], "reviewer")
    q = (await client.get("/api/v1/reviews/queue", headers=h)).json()
    assert [i["severity"] for i in q] == ["critical", "high"]  # critical first
    assert all(i["review_status"] == "pending" for i in q)
    s = (await client.get("/api/v1/dashboard/summary", headers=h)).json()
    assert s["pending_reviews"] == 2
    await client.post(f"/api/v1/run-items/{crit}/reviews", json=REJECT, headers=h)
    assert [i["case_key"] for i in (await client.get("/api/v1/reviews/queue", headers=h)).json()] == ["TC-1"]
    assert len((await client.get("/api/v1/reviews/queue?status=resolved", headers=h)).json()) == 1
    assert (await client.get("/api/v1/dashboard/summary", headers=h)).json()["pending_reviews"] == 1


async def test_disagreement_requires_admin_arbitration(client, rsa_key, two_orgs, owner_engine):
    crit, _, _ = await seed_items(owner_engine, two_orgs[0])
    org = two_orgs[0]
    r1 = await hdr(rsa_key, owner_engine, org, "reviewer", sub="rev-1")
    r2 = await hdr(rsa_key, owner_engine, org, "reviewer", sub="rev-2")
    admin = await hdr(rsa_key, owner_engine, org, "admin", sub="adm-1")
    eng = await hdr(rsa_key, owner_engine, org, "engineer", sub="eng-1")
    url = f"/api/v1/run-items/{crit}"
    assert (await client.post(f"{url}/reviews", json=REJECT, headers=r1)).json()["status"] == "agreed"
    d = (await client.post(f"{url}/reviews", json=ACCEPT, headers=r2)).json()
    assert d["status"] == "disputed" and d["final_decision"] is None and len(d["reviews"]) == 2
    assert [i["review_status"] for i in (await client.get("/api/v1/reviews/queue?status=disputed", headers=r1)).json()] == ["disputed"]
    assert (await client.get("/api/v1/dashboard/summary", headers=r1)).json()["pending_reviews"] >= 1  # still open

    body = {"final_decision": "reject", "justification": "Section does not exist in the source document."}
    assert (await client.post(f"{url}/arbitrate", json=body, headers=r1)).status_code == 403   # reviewers cannot arbitrate
    assert (await client.post(f"{url}/arbitrate", json=body, headers=eng)).status_code == 403
    a = (await client.post(f"{url}/arbitrate", json=body, headers=admin)).json()
    assert a["status"] == "arbitrated" and a["final_decision"] == "reject"
    # final: no more reviews, no second arbitration
    assert (await client.post(f"{url}/reviews", json=ACCEPT, headers=r1)).status_code == 409
    assert (await client.post(f"{url}/arbitrate", json=body, headers=admin)).status_code == 409


async def test_arbitrating_a_non_disputed_case_is_rejected(client, rsa_key, two_orgs, owner_engine):
    crit, _, _ = await seed_items(owner_engine, two_orgs[0])
    admin = await hdr(rsa_key, owner_engine, two_orgs[0], "admin")
    body = {"final_decision": "accept", "justification": "Because I said so, for ten chars."}
    assert (await client.post(f"/api/v1/run-items/{crit}/arbitrate", json=body, headers=admin)).status_code == 409


async def test_reviewer_can_change_mind_and_latest_counts_but_history_is_kept(client, rsa_key, two_orgs, owner_engine):
    crit, _, _ = await seed_items(owner_engine, two_orgs[0])
    h = await hdr(rsa_key, owner_engine, two_orgs[0], "reviewer", sub="rev-x")
    url = f"/api/v1/run-items/{crit}/reviews"
    await client.post(url, json=ACCEPT, headers=h)
    d = (await client.post(url, json=REJECT, headers=h)).json()
    assert d["status"] == "agreed" and d["final_decision"] == "reject" and d["my_decision"] == "reject"
    async with owner_engine.connect() as c:
        n = (await c.execute(text("SELECT count(*) FROM reviews WHERE run_item_id=:i"), {"i": crit})).scalar_one()
    assert n == 2  # append-only: the first review is still on record


async def test_reviews_are_audited_and_tenant_isolated(client, rsa_key, two_orgs, owner_engine):
    crit, _, _ = await seed_items(owner_engine, two_orgs[0])
    ha = await hdr(rsa_key, owner_engine, two_orgs[0], "reviewer")
    hb = await hdr(rsa_key, owner_engine, two_orgs[1], "reviewer")
    assert (await client.post(f"/api/v1/run-items/{crit}/reviews", json=REJECT, headers=hb)).status_code == 404
    assert (await client.get(f"/api/v1/run-items/{crit}/review", headers=hb)).status_code == 404
    assert (await client.get("/api/v1/reviews/queue?status=all", headers=hb)).json() == []
    await client.post(f"/api/v1/run-items/{crit}/reviews", json=REJECT, headers=ha)
    async with owner_engine.connect() as c:
        acts = (await c.execute(text("SELECT action FROM audit_log WHERE org_id=:o"), {"o": two_orgs[0]})).scalars().all()
    assert "review.submit" in acts
