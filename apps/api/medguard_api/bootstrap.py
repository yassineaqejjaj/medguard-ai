"""Idempotently create organisations (runs as schema owner; the app role cannot create orgs).

Usage: python -m medguard_api.bootstrap demo-org:"Demo Organisation" other-org:"Other Organisation"
"""
import asyncio
import os
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main(specs: list[str]) -> None:
    engine = create_async_engine(os.environ["MEDGUARD_MIGRATION_URL"])
    async with engine.begin() as c:
        for spec in specs:
            slug, _, name = spec.partition(":")
            await c.execute(
                text("INSERT INTO organizations (id, name, slug, retention_days) VALUES (:i, :n, :s, 365) "
                     "ON CONFLICT (slug) DO NOTHING"),
                {"i": uuid.uuid4(), "n": name or slug, "s": slug},
            )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
