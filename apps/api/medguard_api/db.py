import uuid
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def set_tenant(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Bind the transaction to a tenant; Postgres RLS policies read this setting."""
    await session.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_id)})


async def tenant_session(org_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        async with session.begin():
            await set_tenant(session, org_id)
            yield session
