import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from medguard_api.models import Base

target_metadata = Base.metadata
# Migrations run as the schema owner, not as the RLS-restricted application role.
URL = os.environ.get("MEDGUARD_MIGRATION_URL", "postgresql+asyncpg://medguard:medguard@localhost:5432/medguard")


def _run(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _online():
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_online())
