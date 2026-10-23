import os
import subprocess
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

OWNER_URL = os.environ.get("MEDGUARD_TEST_OWNER_URL", "postgresql+asyncpg://medguard:medguard@localhost:55432/medguard")
APP_URL = os.environ.get("MEDGUARD_TEST_APP_URL", "postgresql+asyncpg://medguard_app:medguard_app@localhost:55432/medguard")


@pytest.fixture(scope="session", autouse=True)
def migrated():
    env = {**os.environ, "MEDGUARD_MIGRATION_URL": OWNER_URL}
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)


@pytest_asyncio.fixture(scope="session")
async def owner_engine(migrated):
    e = create_async_engine(OWNER_URL)
    yield e
    await e.dispose()


@pytest_asyncio.fixture(scope="session")
async def app_engine(migrated):
    e = create_async_engine(APP_URL)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def two_orgs(owner_engine):
    ids = []
    async with owner_engine.begin() as c:
        for n in ("a", "b"):
            oid = uuid.uuid4()
            await c.execute(
                text("INSERT INTO organizations (id,name,slug,retention_days) VALUES (:i,:n,:s,365)"),
                {"i": oid, "n": f"Org {n}", "s": f"org-{n}-{oid.hex[:6]}"},
            )
            ids.append(oid)
    return ids
