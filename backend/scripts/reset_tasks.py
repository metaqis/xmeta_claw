import asyncio

from sqlalchemy import text

from app.database.db import async_session, init_db
from app.scheduler.tasks import TASK_DEFINITIONS, apply_task_config, ensure_task_configs


async def reset_tasks():
    await init_db()
    async with async_session() as db:
        await db.execute(text("TRUNCATE TABLE task_run_logs RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE TABLE task_runs RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE TABLE task_configs RESTART IDENTITY CASCADE"))
        await db.commit()

    await ensure_task_configs()
    for task_id in TASK_DEFINITIONS.keys():
        try:
            await apply_task_config(task_id)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(reset_tasks())

