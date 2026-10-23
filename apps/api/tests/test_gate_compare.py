import json
import uuid

import pytest

from medguard_api.gates import GateRules, evaluate
from medguard_api.outcomes import Outcome
from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401
from tests.test_engine_e2e import (allow_private, no_enqueue, run_and_wait, servers, setup, SUITE)  # noqa: F401


# ---- unit: the gate cannot be argued with by an average ----------------------------------

def O(i, sev="low", eff="passed", open_review=False, cat="c", human=None):
    return Outcome(uuid.uuid4(), f"TC-{i}", 1, cat, sev, "q", "failed" if eff == "failed" else "passed", eff,
                   open_review, open_review, human)


def test_one_critical_failure_fails_the_gate_despite_a_99_percent_pass_rate():
    outs = [O(i) for i in range(99)] + [O(99, "critical", "failed")]
    status, d = evaluate(outs, GateRules(), None)
    assert status == "FAIL" and d["counts"]["pass_rate"] == 0.99
    assert [c["status"] for c in d["criteria"] if c["name"] == "Critical failures"] == ["fail"]


def test_review_required_when_clean_but_reviews_open_and_pass_when_closed():
    outs = [O(i) for i in range(20)] + [O(20, "high", "passed", open_review=True)]
    assert evaluate(outs, GateRules(), None)[0] == "REVIEW_REQUIRED"
    outs[-1] = O(20, "high", "passed", open_review=False)
    assert evaluate(outs, GateRules(), None)[0] == "PASS"


def test_blocking_failure_beats_pending_review_and_low_pass_rate_fails():
    outs = [O(0, "critical", "failed", open_review=True)] + [O(i) for i in range(1, 30)]
    assert evaluate(outs, GateRules(), None)[0] == "FAIL"
    outs = [O(i, eff="failed") for i in range(5)] + [O(i) for i in range(5, 10)]
    assert evaluate(outs, GateRules(), None)[0] == "FAIL"  # 50% < 90%


def test_category_floor_and_regression_limit_and_empty_run():
    outs = [O(i, cat="Citation") for i in range(9)] + [O(9, eff="failed", cat="Citation")] + [O(i, cat="Other") for i in range(10, 40)]
    rules = GateRules(min_category_pass_rate={"Citation": 0.95})
    assert evaluate(outs, rules, None)[0] == "FAIL"   # overall 97.5% but the category is below its floor
    assert evaluate([O(i) for i in range(10)], GateRules(max_new_regressions=0), 2)[0] == "FAIL"
    assert evaluate([], GateRules(), None)[0] == "FAIL"  # nothing evaluated is not a pass


def test_human_acceptance_of_a_flagged_critical_failure_is_what_clears_it():
    cleared = O(0, "critical", "passed", human="accept")
    assert evaluate([cleared] + [O(i) for i in range(1, 20)], GateRules(), None)[0] == "PASS"


# ---- integration -------------------------------------------------------------------------

async def hdr(rsa_key, owner_engine, org, role, sub=None):
    return auth(token(rsa_key, await slug_of(owner_engine, org), role, sub=sub))


async def two_runs(client, h, servers, org, rsa_key=None):
    suite_id, vers = await setup(client, h, servers, org)
    good, good_id = await run_and_wait(client, h, org, vers["v1"], suite_id)
    bad, bad_id = await run_and_wait(client, h, org, vers["v2"], suite_id)
    return suite_id, vers, good_id, bad_id


@pytest.fixture
def no_judge(monkeypatch):
    from medguard_api import config
    monkeypatch.delenv("MEDGUARD_JUDGE_URL", raising=False)
    config.get_settings.cache_clear()


async def test_compare_surfaces_regressions_and_never_hides_critical_ones(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    h = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers, good, bad = await two_runs(client, h, servers, org)
    c = (await client.get(f"/api/v1/compare?baseline_run={good}&candidate_run={bad}", headers=h)).json()
    assert c["verdict"] == "worse" and len(c["regressions"]) == 9 and c["critical_regressions"] == 3
    assert c["fixed"] == [] and c["unchanged_failures"] == []
    assert [r["severity"] for r in c["regressions"][:3]] == ["critical"] * 3  # critical first
    assert c["baseline"]["version"] == "v1" and c["candidate"]["version"] == "v2"
    assert c["baseline"]["pass_rate"] == 1.0 and c["candidate"]["critical_failures"] == 3
    cats = {r["category"]: r for r in c["categories"]}
    assert cats["Citation Accuracy"]["baseline"] == 1.0 and cats["Citation Accuracy"]["candidate"] < 1.0
    # reversed direction: v2 -> v1 fixes the same 9 and regresses none
    r = (await client.get(f"/api/v1/compare?baseline_run={bad}&candidate_run={good}", headers=h)).json()
    assert r["verdict"] == "better" and len(r["fixed"]) == 9 and r["regressions"] == []


async def test_compare_rejects_mismatched_inputs_and_other_tenants(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    h = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers, good, bad = await two_runs(client, h, servers, org)
    # a different suite on the same system cannot be compared
    s2 = (await client.post("/api/v1/suites", json={"name": "Other"}, headers=h)).json()["id"]
    await client.post(f"/api/v1/suites/{s2}/import", json={"format": "json", "content": json.dumps({"cases": SUITE["cases"][:2]})}, headers=h)
    other, _ = await run_and_wait(client, h, org, vers["v1"], s2)
    assert (await client.get(f"/api/v1/compare?baseline_run={good}&candidate_run={other['id']}", headers=h)).status_code == 422
    hb = await hdr(rsa_key, owner_engine, two_orgs[1], "engineer")
    assert (await client.get(f"/api/v1/compare?baseline_run={good}&candidate_run={bad}", headers=hb)).status_code == 404


async def test_gate_lifecycle_review_then_pass_then_signed_release(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer", "eng")
    rev = await hdr(rsa_key, owner_engine, org, "reviewer", "rev")
    adm = await hdr(rsa_key, owner_engine, org, "admin", "adm")
    suite_id, vers, good, bad = await two_runs(client, eng, servers, org)

    # bad version: blocked, whatever else is true
    g_bad = (await client.post(f"/api/v1/runs/{bad}/gate", json={"baseline_run_id": good}, headers=eng)).json()
    assert g_bad["status"] == "FAIL" and g_bad["details"]["counts"]["critical_failures"] == 3
    assert g_bad["policy"]["max_critical_failures"] == 0
    d = {"decision": "release", "justification": "We need it shipped by Friday, honestly."}
    assert (await client.post(f"/api/v1/gates/{g_bad['id']}/decision", json=d, headers=adm)).status_code == 409  # cannot release on FAIL
    blk = await client.post(f"/api/v1/gates/{g_bad['id']}/decision", json={"decision": "block", "justification": "Regressions on critical cases."}, headers=adm)
    assert blk.status_code == 201 and blk.json()["decisions"][0]["decision"] == "block"

    # good version: clean automatically but 10 flagged results (no judge) => REVIEW_REQUIRED, not PASS
    g1 = (await client.post(f"/api/v1/runs/{good}/gate", json={}, headers=eng)).json()
    assert g1["status"] == "REVIEW_REQUIRED" and g1["details"]["counts"]["open_reviews"] == 10
    assert (await client.post(f"/api/v1/gates/{g1['id']}/decision", json=d, headers=adm)).status_code == 409

    queue = (await client.get(f"/api/v1/reviews/queue?run_id={good}", headers=rev)).json()
    assert len(queue) == 10
    for it in queue:
        r = await client.post(f"/api/v1/run-items/{it['id']}/reviews", headers=rev, json={
            "decision": "accept", "justification": "Answer matches the source document."})
        assert r.status_code == 201, r.text
    g2 = (await client.post(f"/api/v1/runs/{good}/gate", json={}, headers=eng)).json()
    assert g2["status"] == "PASS" and g2["details"]["counts"]["open_reviews"] == 0

    # the older evaluation is stale; only the latest one can be signed
    stale = await client.post(f"/api/v1/gates/{g1['id']}/decision", json=d, headers=adm)
    assert stale.status_code == 409
    ok_body = {"decision": "release", "justification": "All criteria met and reviewed by Dr. Reviewer."}
    assert (await client.post(f"/api/v1/gates/{g2['id']}/decision", json=ok_body, headers=eng)).status_code == 403
    assert (await client.post(f"/api/v1/gates/{g2['id']}/decision", json=ok_body, headers=rev)).status_code == 403
    done = await client.post(f"/api/v1/gates/{g2['id']}/decision", json=ok_body, headers=adm)
    assert done.status_code == 201 and done.json()["decisions"][0]["decision"] == "release"
    assert (await client.post(f"/api/v1/gates/{g2['id']}/decision", json=ok_body, headers=adm)).status_code == 409
    rows = (await client.get("/api/v1/gates", headers=eng)).json()
    assert {r["status"] for r in rows} == {"FAIL", "PASS"} and any(r["decision"] == "release" for r in rows)


async def test_gate_requires_completed_run_engineer_role_and_valid_policy(
        client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    adm = await hdr(rsa_key, owner_engine, org, "admin")
    suite_id, vers, good, bad = await two_runs(client, eng, servers, org)
    sysid = vers["system"]
    rev = await hdr(rsa_key, owner_engine, org, "reviewer")
    assert (await client.post(f"/api/v1/runs/{good}/gate", json={}, headers=rev)).status_code == 403
    assert (await client.put(f"/api/v1/systems/{sysid}/gate-policy", json=GateRules().model_dump(), headers=eng)).status_code == 403
    assert (await client.put(f"/api/v1/systems/{sysid}/gate-policy", json={"min_pass_rat": 0.5}, headers=adm)).status_code == 422
    assert (await client.put(f"/api/v1/systems/{sysid}/gate-policy", json={"min_pass_rate": 1.5}, headers=adm)).status_code == 422
    ok = await client.put(f"/api/v1/systems/{sysid}/gate-policy", json={"min_pass_rate": 0.5, "max_critical_failures": 3,
                                                                         "require_reviews_resolved": False}, headers=adm)
    assert ok.status_code == 200
    # policy is snapshotted into each evaluation: loosening it later cannot rewrite history
    g = (await client.post(f"/api/v1/runs/{bad}/gate", json={}, headers=eng)).json()
    assert g["policy"]["min_pass_rate"] == 0.5
    assert (await client.get(f"/api/v1/systems/{sysid}/gate-policy", headers=eng)).json()["max_critical_failures"] == 3


async def test_ci_token_flow(client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    adm = await hdr(rsa_key, owner_engine, org, "admin")
    suite_id, vers, good, bad = await two_runs(client, eng, servers, org)
    await client.post(f"/api/v1/runs/{bad}/gate", json={}, headers=eng)

    assert (await client.post("/api/v1/tokens", json={"name": "ci"}, headers=eng)).status_code == 403
    t = (await client.post("/api/v1/tokens", json={"name": "gitlab-ci"}, headers=adm)).json()
    raw = t["token"]
    assert raw.startswith("mgt_")
    listed = (await client.get("/api/v1/tokens", headers=adm)).text
    assert raw not in listed and "token_hash" not in listed  # only a hash is stored, never returned
    ci = {"Authorization": f"Bearer {raw}"}

    r = (await client.get("/api/v1/ci/gate?system=Demo assistant&version=v2", headers=ci)).json()
    assert r["status"] == "FAIL" and r["exit_code"] == 1 and any("Critical failures" in x for x in r["reasons"])
    r = (await client.get("/api/v1/ci/gate?system=Demo assistant&version=v1", headers=ci)).json()
    assert r["status"] == "NOT_EVALUATED" and r["exit_code"] == 3

    # a CI token opens nothing else
    assert (await client.get("/api/v1/me", headers=ci)).status_code == 401
    assert (await client.get("/api/v1/runs", headers=ci)).status_code == 401
    assert (await client.get("/api/v1/ci/gate?system=x&version=y")).status_code == 401
    assert (await client.get("/api/v1/ci/gate?system=x&version=y", headers={"Authorization": "Bearer mgt_bogus"})).status_code == 401
    # an org-B token cannot see org-A's application
    tb = (await client.post("/api/v1/tokens", json={"name": "b"}, headers=await hdr(rsa_key, owner_engine, two_orgs[1], "admin"))).json()["token"]
    assert (await client.get("/api/v1/ci/gate?system=Demo assistant&version=v2", headers={"Authorization": f"Bearer {tb}"})).status_code == 404
    # revoked tokens stop working
    assert (await client.delete(f"/api/v1/tokens/{t['id']}", headers=adm)).status_code == 204
    assert (await client.get("/api/v1/ci/gate?system=Demo assistant&version=v2", headers=ci)).status_code == 401


async def test_run_not_gated_yet_is_a_normal_empty_state(client, rsa_key, two_orgs, owner_engine, servers, no_enqueue, no_judge):
    org = two_orgs[0]
    eng = await hdr(rsa_key, owner_engine, org, "engineer")
    suite_id, vers, good, bad = await two_runs(client, eng, servers, org)
    r = await client.get(f"/api/v1/runs/{good}/gate", headers=eng)
    assert r.status_code == 200 and r.json() is None
