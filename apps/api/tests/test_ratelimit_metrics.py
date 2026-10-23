import time

from medguard_api import ratelimit
from tests.test_auth_rbac_audit import auth, client, rsa_key, slug_of, token  # noqa: F401


async def test_rate_limit_is_per_user_and_returns_429_with_retry_after(client, rsa_key, two_orgs, owner_engine, monkeypatch):
    from medguard_api import config
    monkeypatch.setenv("MEDGUARD_RATE_LIMIT_PER_MINUTE", "3")
    config.get_settings.cache_clear()
    ratelimit.reset_memory()
    slug = await slug_of(owner_engine, two_orgs[0])
    a = auth(token(rsa_key, slug, "engineer", sub="user-a"))
    b = auth(token(rsa_key, slug, "engineer", sub="user-b"))
    codes = [(await client.get("/api/v1/me", headers=a)).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    r = await client.get("/api/v1/me", headers=a)
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert (await client.get("/api/v1/me", headers=b)).status_code == 200  # another user is unaffected


async def test_rate_limit_window_resets(monkeypatch):
    from medguard_api import config
    monkeypatch.setenv("MEDGUARD_RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("MEDGUARD_RATE_LIMIT_PER_MINUTE", "1")
    config.get_settings.cache_clear()
    ratelimit.reset_memory()
    await ratelimit.check("k")
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await ratelimit.check("k")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 61)
    await ratelimit.check("k")  # new window


async def test_limiter_fails_open_when_valkey_is_down(monkeypatch):
    from medguard_api import config
    monkeypatch.setenv("MEDGUARD_RATE_LIMIT_BACKEND", "valkey")
    monkeypatch.setenv("MEDGUARD_VALKEY_URL", "redis://127.0.0.1:1/0")
    config.get_settings.cache_clear()
    ratelimit._valkey = None
    await ratelimit.check("anything")  # no exception: availability over strictness for this control


async def test_metrics_endpoint_exposes_route_templates_not_ids(client, rsa_key, two_orgs, owner_engine):
    slug = await slug_of(owner_engine, two_orgs[0])
    h = auth(token(rsa_key, slug, "engineer"))
    await client.get("/api/v1/runs/00000000-0000-0000-0000-000000000000", headers=h)
    text = (await client.get("/metrics")).text
    assert 'route="/api/v1/runs/{run_id}"' in text and "00000000-0000" not in text
    r = await client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
