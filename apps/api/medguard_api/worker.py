import asyncio
import uuid

from celery import Celery

from .config import get_settings

app = Celery("medguard", broker=get_settings().valkey_url, backend=None)
app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, task_time_limit=3600)


@app.task(name="medguard.run_evaluation")
def run_evaluation(org_id: str, run_id: str) -> None:
    from .evaluation.engine import execute_run
    from . import db

    async def _go():
        try:
            await execute_run(uuid.UUID(org_id), uuid.UUID(run_id))
        finally:
            await db.get_engine().dispose()

    asyncio.run(_go())


def enqueue_run(org_id: uuid.UUID, run_id: uuid.UUID) -> None:
    run_evaluation.apply_async(args=[str(org_id), str(run_id)], countdown=2)
