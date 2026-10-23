import csv
import io
import json

from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401

CASE = {"category": "Document Faithfulness", "input": "When is the review due?", "severity": "medium",
        "criteria": ["faithfulness"], "pass_conditions": {"must_contain": ["4 weeks"]}}


async def hdr(rsa_key, owner_engine, org, role="engineer"):
    return auth(token(rsa_key, await slug_of(owner_engine, org), role))


async def make_suite(client, h, name="S"):
    r = await client.post("/api/v1/suites", json={"name": name}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_case_crud_versioning_duplicate_and_validation(client, rsa_key, two_orgs, owner_engine):
    h = await hdr(rsa_key, owner_engine, two_orgs[0])
    sid = await make_suite(client, h)
    c1 = (await client.post(f"/api/v1/suites/{sid}/cases", json=CASE, headers=h)).json()
    assert c1["case_key"] == "TC-0001" and c1["version"] == 1 and c1["validation_status"] == "draft"

    edited = (await client.put(f"/api/v1/cases/{c1['id']}", json={**CASE, "input": "Edited?"}, headers=h)).json()
    assert edited["case_key"] == "TC-0001" and edited["version"] == 2 and edited["id"] != c1["id"]
    # the old version is no longer current, and can't be edited again
    assert (await client.put(f"/api/v1/cases/{c1['id']}", json=CASE, headers=h)).status_code == 409
    cases = (await client.get(f"/api/v1/suites/{sid}", headers=h)).json()
    assert [c["version"] for c in cases] == [2]

    dup = (await client.post(f"/api/v1/cases/{edited['id']}/duplicate", headers=h)).json()
    assert dup["case_key"] == "TC-0002" and dup["input"] == "Edited?"

    # validation needs a reviewer; engineers can't self-validate
    assert (await client.post(f"/api/v1/cases/{dup['id']}/validation", json={"status": "validated", "justification": "ok"},
                              headers=h)).status_code == 403
    hr = await hdr(rsa_key, owner_engine, two_orgs[0], "reviewer")
    v = await client.post(f"/api/v1/cases/{dup['id']}/validation", json={"status": "validated", "justification": "clinically sound"}, headers=hr)
    assert v.status_code == 200 and v.json()["validation_status"] == "validated"
    # editing resets the human validation
    again = (await client.put(f"/api/v1/cases/{dup['id']}", json=CASE, headers=h)).json()
    assert again["validation_status"] == "draft"


async def test_validation_rejects_unknown_condition_keys_and_criteria(client, rsa_key, two_orgs, owner_engine):
    h = await hdr(rsa_key, owner_engine, two_orgs[0])
    sid = await make_suite(client, h)
    r = await client.post(f"/api/v1/suites/{sid}/cases", json={**CASE, "pass_conditions": {"must_contian": ["x"]}}, headers=h)
    assert r.status_code == 422
    r = await client.post(f"/api/v1/suites/{sid}/cases", json={**CASE, "criteria": ["vibes"]}, headers=h)
    assert r.status_code == 422
    r = await client.post(f"/api/v1/suites/{sid}/cases", json={**CASE, "severity": "catastrophic"}, headers=h)
    assert r.status_code == 422


async def test_json_import_export_roundtrip_and_atomic_rejection(client, rsa_key, two_orgs, owner_engine):
    h = await hdr(rsa_key, owner_engine, two_orgs[0])
    sid = await make_suite(client, h)
    good = json.dumps({"cases": [CASE, {**CASE, "input": "Second?"}]})
    r = await client.post(f"/api/v1/suites/{sid}/import", json={"format": "json", "content": good}, headers=h)
    assert r.json() == {"created": 2, "new_versions": 0}

    bad = json.dumps({"cases": [CASE, {**CASE, "severity": "nope"}]})
    r = await client.post(f"/api/v1/suites/{sid}/import", json={"format": "json", "content": bad}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["rows"][0]["row"] == 2
    assert len((await client.get(f"/api/v1/suites/{sid}", headers=h)).json()) == 2  # nothing partially imported

    exported = (await client.get(f"/api/v1/suites/{sid}/export?format=json", headers=h)).json()
    assert [c["case_key"] for c in exported["cases"]] == ["TC-0001", "TC-0002"]
    # re-importing the export updates by key => new versions, no duplicates
    r = await client.post(f"/api/v1/suites/{sid}/import", json={"format": "json", "content": json.dumps(exported)}, headers=h)
    assert r.json() == {"created": 0, "new_versions": 2}
    assert len((await client.get(f"/api/v1/suites/{sid}", headers=h)).json()) == 2


async def test_csv_import_export_and_formula_injection_is_neutralised(client, rsa_key, two_orgs, owner_engine):
    h = await hdr(rsa_key, owner_engine, two_orgs[0])
    sid = await make_suite(client, h)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["category", "input", "severity", "criteria", "pass_conditions"])
    w.writerow(["Safety", "=HYPERLINK(\"http://evil\",\"x\")", "high", "boundaries;relevance", '{"must_contain": ["ok"]}'])
    r = await client.post(f"/api/v1/suites/{sid}/import", json={"format": "csv", "content": buf.getvalue()}, headers=h)
    assert r.status_code == 200, r.text
    case = (await client.get(f"/api/v1/suites/{sid}", headers=h)).json()[0]
    assert case["criteria"] == ["boundaries", "relevance"]
    out = (await client.get(f"/api/v1/suites/{sid}/export?format=csv", headers=h)).text
    row = list(csv.DictReader(io.StringIO(out)))[0]
    assert row["input"].startswith("'=")  # a spreadsheet will not execute it


async def test_csv_errors_are_reported(client, rsa_key, two_orgs, owner_engine):
    h = await hdr(rsa_key, owner_engine, two_orgs[0])
    sid = await make_suite(client, h)
    r = await client.post(f"/api/v1/suites/{sid}/import", json={"format": "csv", "content": "foo,bar\n1,2\n"}, headers=h)
    assert r.status_code == 422 and "missing required columns" in r.text
    r = await client.post(f"/api/v1/suites/{sid}/import", json={"format": "json", "content": "{not json"}, headers=h)
    assert r.status_code == 422


async def test_reorder(client, rsa_key, two_orgs, owner_engine):
    h = await hdr(rsa_key, owner_engine, two_orgs[0])
    sid = await make_suite(client, h)
    ids = [(await client.post(f"/api/v1/suites/{sid}/cases", json={**CASE, "input": f"q{i}"}, headers=h)).json()["id"] for i in range(3)]
    r = await client.put(f"/api/v1/suites/{sid}/order", json={"case_ids": ids[::-1]}, headers=h)
    assert [c["id"] for c in r.json()] == ids[::-1]
    assert (await client.put(f"/api/v1/suites/{sid}/order", json={"case_ids": ids[:2]}, headers=h)).status_code == 422


async def test_suites_are_tenant_isolated_and_viewer_is_read_only(client, rsa_key, two_orgs, owner_engine):
    ha = await hdr(rsa_key, owner_engine, two_orgs[0])
    hb = await hdr(rsa_key, owner_engine, two_orgs[1])
    sid = await make_suite(client, ha, "Private")
    assert (await client.get(f"/api/v1/suites/{sid}", headers=hb)).status_code == 404
    assert (await client.post(f"/api/v1/suites/{sid}/cases", json=CASE, headers=hb)).status_code == 404
    assert "Private" not in [s["name"] for s in (await client.get("/api/v1/suites", headers=hb)).json()]
    hv = await hdr(rsa_key, owner_engine, two_orgs[0], "viewer")
    assert (await client.post("/api/v1/suites", json={"name": "x"}, headers=hv)).status_code == 403
    assert (await client.get("/api/v1/suites", headers=hv)).status_code == 200
