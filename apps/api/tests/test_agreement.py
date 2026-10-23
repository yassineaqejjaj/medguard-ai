import pytest
from sqlalchemy import text

from medguard_api.evaluation.agreement import agreement, cohen_kappa
from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401
from tests.test_reviews import ACCEPT, REJECT, seed_items


def test_kappa_perfect_none_and_chance_levels():
    assert cohen_kappa(["pass", "fail", "pass", "fail"], ["pass", "fail", "pass", "fail"]) == 1.0
    assert cohen_kappa(["pass", "pass", "fail", "fail"], ["fail", "fail", "pass", "pass"]) == -1.0
    assert cohen_kappa(["pass", "pass", "pass", "pass"], ["pass", "pass", "pass", "pass"]) == 1.0
    assert cohen_kappa([], []) is None
    # known textbook value: po=0.7, pe=0.5 -> kappa 0.4
    a = ["pass"] * 5 + ["fail"] * 5
    b = ["pass"] * 4 + ["fail"] * 1 + ["pass"] * 2 + ["fail"] * 3
    assert cohen_kappa(a, b) == pytest.approx(0.4)


def test_agreement_flags_false_passes_and_small_samples():
    a = agreement([("pass", "fail"), ("pass", "pass"), ("fail", "fail"), ("fail", "pass")])
    assert a.n == 4 and a.observed == 0.5 and a.judge_false_pass == 1 and a.judge_false_fail == 1 and not a.sufficient
    assert agreement([("pass", "pass")] * 30).sufficient


async def test_agreement_endpoint_pairs_judge_verdicts_with_human_decisions(client, rsa_key, two_orgs, owner_engine):
    org = two_orgs[0]
    crit, high, _ = await seed_items(owner_engine, org)
    async with owner_engine.begin() as c:  # the critical item was judged PASS by the LLM, the high one judged FAIL
        for item, status in ((crit, "pass"), (high, "fail")):
            await c.execute(text(
                "INSERT INTO criterion_results (id,org_id,run_item_id,kind,criterion,score,status,justification,evidence,confidence,requires_review,judge_prompt_version) "
                "VALUES (gen_random_uuid(),:o,:i,'llm_judge','faithfulness',0.9,:s,'x','[]',0.9,false,'judge-v1')"), {"o": org, "i": item, "s": status})
    rev = auth(token(rsa_key, await slug_of(owner_engine, org), "reviewer"))
    await client.post(f"/api/v1/run-items/{crit}/reviews", json=REJECT, headers=rev)   # human: not acceptable
    await client.post(f"/api/v1/run-items/{high}/reviews", json=ACCEPT, headers=rev)   # human: acceptable
    r = (await client.get("/api/v1/judge/agreement", headers=rev)).json()
    assert r["n"] == 2 and r["judge_false_pass"] == 1 and r["judge_false_fail"] == 1 and r["sufficient"] is False
    assert r["kappa"] == -1.0 and "indicative" in r["note"]
    eng = auth(token(rsa_key, await slug_of(owner_engine, org), "engineer"))
    assert (await client.get("/api/v1/judge/agreement", headers=eng)).status_code == 403
