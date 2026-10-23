import base64
import os
import time
import uuid

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

ISSUER = "http://idp.test/realms/medguard"
AUD = "medguard-api"


@pytest.fixture(scope="session")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest_asyncio.fixture
async def client(monkeypatch, rsa_key, migrated):
    from medguard_api import config, db, security
    monkeypatch.setenv("MEDGUARD_DATABASE_URL", os.environ.get(
        "MEDGUARD_TEST_APP_URL", "postgresql+asyncpg://medguard_app:medguard_app@localhost:55432/medguard"))
    monkeypatch.setenv("MEDGUARD_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("MEDGUARD_OIDC_AUDIENCE", AUD)
    monkeypatch.setenv("MEDGUARD_EVIDENCE_BACKEND", "memory")
    monkeypatch.setenv("MEDGUARD_RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("MEDGUARD_SECRET_KEY_B64", base64.b64encode(os.urandom(32)).decode())
    config.get_settings.cache_clear()
    db._engine = db._sessionmaker = None
    # Serve our test public key instead of fetching JWKS from a real IdP.
    monkeypatch.setattr(security, "_signing_key", lambda token: rsa_key.public_key())
    from medguard_api.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await db.get_engine().dispose()
    db._engine = db._sessionmaker = None


def token(rsa_key, org_slug, role="engineer", sub=None, **over):
    claims = {"iss": ISSUER, "aud": AUD, "sub": sub or str(uuid.uuid4()), "exp": int(time.time()) + 300,
              "email": "u@example.test", "org": org_slug, "realm_access": {"roles": [role]}, **over}
    return jwt.encode(claims, rsa_key, algorithm="RS256")


def auth(t):
    return {"Authorization": f"Bearer {t}"}


async def slug_of(owner_engine, org_id):
    async with owner_engine.connect() as c:
        return (await c.execute(text("SELECT slug FROM organizations WHERE id=:i"), {"i": org_id})).scalar_one()


async def test_missing_and_bad_tokens_rejected(client, rsa_key, two_orgs, owner_engine):
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await client.get("/api/v1/me", headers=auth("garbage"))).status_code == 401
    slug = await slug_of(owner_engine, two_orgs[0])
    expired = token(rsa_key, slug, exp=int(time.time()) - 10)
    assert (await client.get("/api/v1/me", headers=auth(expired))).status_code == 401
    wrong_aud = token(rsa_key, slug, aud="other")
    assert (await client.get("/api/v1/me", headers=auth(wrong_aud))).status_code == 401
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert (await client.get("/api/v1/me", headers=auth(token(other_key, slug)))).status_code == 401


async def test_me_provisions_user_in_token_tenant(client, rsa_key, two_orgs, owner_engine):
    slug = await slug_of(owner_engine, two_orgs[0])
    r = await client.get("/api/v1/me", headers=auth(token(rsa_key, slug, "reviewer")))
    assert r.status_code == 200
    assert r.json()["org_id"] == str(two_orgs[0]) and r.json()["role"] == "reviewer"


async def test_unknown_org_or_role_forbidden(client, rsa_key):
    assert (await client.get("/api/v1/me", headers=auth(token(rsa_key, "no-such-org")))).status_code == 403
    t = token(rsa_key, "x", realm_access={"roles": ["offline_access"]})
    assert (await client.get("/api/v1/me", headers=auth(t))).status_code == 403


async def test_audit_requires_admin_and_chain_verifies(client, rsa_key, two_orgs, owner_engine):
    from medguard_api import audit, db
    org = two_orgs[1]
    slug = await slug_of(owner_engine, org)
    assert (await client.get("/api/v1/audit", headers=auth(token(rsa_key, slug, "engineer")))).status_code == 403

    async with db.sessionmaker()() as s, s.begin():
        await db.set_tenant(s, org)
        for i in range(3):
            await audit.record(s, org, None, "system.create", "ai_system", str(i), after={"n": i})
    r = await client.get("/api/v1/audit", headers=auth(token(rsa_key, slug, "admin")))
    assert r.status_code == 200 and r.json()["chain_valid"] is True
    assert len(r.json()["entries"]) >= 3


async def test_tampered_audit_chain_detected(client, rsa_key, two_orgs, owner_engine):
    from medguard_api import audit, db
    org = two_orgs[0]
    async with db.sessionmaker()() as s, s.begin():
        await db.set_tenant(s, org)
        await audit.record(s, org, None, "a", "t", "1", after={"v": 1})
        await audit.record(s, org, None, "b", "t", "2", after={"v": 2})
    async with owner_engine.begin() as c:  # attacker with DB owner rights edits history
        await c.execute(text("UPDATE audit_log SET after='{\"v\": 99}' WHERE org_id=:o AND action='a'"), {"o": org})
    async with db.sessionmaker()() as s, s.begin():
        await db.set_tenant(s, org)
        ok, bad = await audit.verify_chain(s, org)
    assert ok is False and bad is not None


def test_secret_encryption_roundtrip_and_randomised(monkeypatch):
    from medguard_api import config, crypto
    monkeypatch.setenv("MEDGUARD_SECRET_KEY_B64", base64.b64encode(os.urandom(32)).decode())
    config.get_settings.cache_clear()
    a, b = crypto.encrypt_secret("s3cret"), crypto.encrypt_secret("s3cret")
    assert a != b and crypto.decrypt_secret(a) == "s3cret"
    monkeypatch.setenv("MEDGUARD_SECRET_KEY_B64", "")
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        crypto.encrypt_secret("x")
