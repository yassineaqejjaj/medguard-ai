import hashlib
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog

GENESIS = "0" * 64


def _digest(prev: str, org_id, actor_id, action, entity_type, entity_id, before, after) -> str:
    payload = json.dumps(
        [prev, str(org_id), str(actor_id) if actor_id else None, action, entity_type, entity_id, before, after],
        sort_keys=True, default=str, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


async def record(session: AsyncSession, org_id: uuid.UUID, actor_id: uuid.UUID | None, action: str,
                 entity_type: str, entity_id: str, before: dict | None = None, after: dict | None = None) -> None:
    # Serialise writers per tenant so the chain cannot fork.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{org_id}"})
    prev = (await session.execute(
        select(AuditLog.hash).where(AuditLog.org_id == org_id).order_by(AuditLog.id.desc()).limit(1)
    )).scalar_one_or_none() or GENESIS
    h = _digest(prev, org_id, actor_id, action, entity_type, entity_id, before, after)
    session.add(AuditLog(org_id=org_id, actor_id=actor_id, action=action, entity_type=entity_type,
                         entity_id=entity_id, before=before, after=after, prev_hash=prev, hash=h))


async def verify_chain(session: AsyncSession, org_id: uuid.UUID) -> tuple[bool, int | None]:
    """Returns (ok, first_bad_id). Stored timestamps are not part of the hash."""
    rows = (await session.execute(select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.id))).scalars()
    prev = GENESIS
    for r in rows:
        if r.prev_hash != prev or r.hash != _digest(prev, r.org_id, r.actor_id, r.action, r.entity_type,
                                                    r.entity_id, r.before, r.after):
            return False, r.id
        prev = r.hash
    return True, None
