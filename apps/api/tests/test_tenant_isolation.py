import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError


async def _tx(engine, org_id):
    conn = await engine.connect()
    tx = await conn.begin()
    if org_id is not None:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_id)})
    return conn, tx


async def _insert_system(conn, org_id, name="sys"):
    await conn.execute(
        text("INSERT INTO ai_systems (id, org_id, name, description, purpose, usage_context, owner, doc_sources) "
             "VALUES (:i,:o,:n,'','','','','[]')"),
        {"i": uuid.uuid4(), "o": org_id, "n": name},
    )


async def test_rows_are_invisible_across_tenants(app_engine, two_orgs):
    a, b = two_orgs
    conn, tx = await _tx(app_engine, a)
    await _insert_system(conn, a, "secret-a")
    await tx.commit(); await conn.close()

    conn, tx = await _tx(app_engine, b)
    rows = (await conn.execute(text("SELECT name FROM ai_systems"))).all()
    await tx.rollback(); await conn.close()
    assert rows == []

    conn, tx = await _tx(app_engine, a)
    rows = (await conn.execute(text("SELECT name FROM ai_systems"))).all()
    await tx.rollback(); await conn.close()
    assert ("secret-a",) in rows


async def test_no_tenant_context_sees_nothing(app_engine, two_orgs):
    conn, tx = await _tx(app_engine, None)
    rows = (await conn.execute(text("SELECT 1 FROM ai_systems"))).all()
    await tx.rollback(); await conn.close()
    assert rows == []


async def test_cannot_write_into_another_tenant(app_engine, two_orgs):
    a, b = two_orgs
    conn, tx = await _tx(app_engine, b)
    with pytest.raises((DBAPIError, ProgrammingError)):
        await _insert_system(conn, a)
    await tx.rollback(); await conn.close()


async def test_audit_log_is_append_only(app_engine, two_orgs):
    a, _ = two_orgs
    conn, tx = await _tx(app_engine, a)
    await conn.execute(
        text("INSERT INTO audit_log (org_id,action,entity_type,entity_id,prev_hash,hash) "
             "VALUES (:o,'x','t','1',:p,:h)"),
        {"o": a, "p": "0" * 64, "h": "1" * 64},
    )
    await tx.commit(); await conn.close()

    for stmt in ("UPDATE audit_log SET action='y'", "DELETE FROM audit_log"):
        conn, tx = await _tx(app_engine, a)
        with pytest.raises((DBAPIError, ProgrammingError)):
            await conn.execute(text(stmt))
        await tx.rollback(); await conn.close()


async def test_org_lookup_by_slug_works_without_context(app_engine, two_orgs, owner_engine):
    async with owner_engine.connect() as c:
        slug = (await c.execute(text("SELECT slug FROM organizations WHERE id=:i"), {"i": two_orgs[0]})).scalar_one()
    conn, tx = await _tx(app_engine, None)
    got = (await conn.execute(text("SELECT org_id_by_slug(:s)"), {"s": slug})).scalar_one()
    await tx.rollback(); await conn.close()
    assert got == two_orgs[0]
