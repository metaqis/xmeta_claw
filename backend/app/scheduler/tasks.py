"""定时任务调度"""
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from app.crawler.archive_crawler import crawl_archives
from app.crawler.calendar_archive_backfill import backfill_archives_for_calendar_range
from app.crawler.calendar_crawler import crawl_calendar_for_date
from app.crawler.launch_detail_crawler import crawl_all_missing_details
from app.database.db import async_session
from app.database.models import TaskConfig, TaskRun

scheduler = AsyncIOScheduler()


async def task_crawl_today_calendar(db):
    logger.info("定时任务: 爬取今日日历")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    await crawl_calendar_for_date(db, today)
    await crawl_calendar_for_date(db, tomorrow)
    await backfill_archives_for_calendar_range(db, today, tomorrow)


async def task_crawl_details(db):
    logger.info("定时任务: 补全发行详情")
    await crawl_all_missing_details(db)


async def task_crawl_archives(db):
    logger.info("定时任务: 爬取藏品列表")
    await crawl_archives(db)


TASK_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "crawl_calendar": {
        "name": "今日日历",
        "description": "爬取今日和明日发行日历",
        "default_schedule_type": "interval",
        "default_interval_seconds": 60 * 60,
        "func": task_crawl_today_calendar,
    },
    "crawl_details": {
        "name": "补全详情",
        "description": "爬取缺少详情的发行记录",
        "default_schedule_type": "interval",
        "default_interval_seconds": 60 * 60,
        "func": task_crawl_details,
    },
    "crawl_archives": {
        "name": "藏品列表",
        "description": "更新藏品库",
        "default_schedule_type": "interval",
        "default_interval_seconds": 6 * 60 * 60,
        "func": task_crawl_archives,
    },
}


def _build_trigger(cfg: TaskConfig):
    if cfg.schedule_type == "cron":
        if not cfg.cron:
            raise ValueError("cron 不能为空")
        return CronTrigger.from_crontab(cfg.cron)
    if not cfg.interval_seconds or cfg.interval_seconds <= 0:
        raise ValueError("interval_seconds 必须为正数")
    return IntervalTrigger(seconds=cfg.interval_seconds)


async def ensure_task_configs():
    async with async_session() as db:
        result = await db.execute(select(TaskConfig.task_id))
        existing = {row[0] for row in result.all()}
        for task_id, meta in TASK_DEFINITIONS.items():
            if task_id in existing:
                continue
            cfg = TaskConfig(
                task_id=task_id,
                name=meta["name"],
                description=meta["description"],
                schedule_type=meta["default_schedule_type"],
                interval_seconds=meta.get("default_interval_seconds"),
                cron=meta.get("default_cron"),
                enabled=True,
            )
            db.add(cfg)
        await db.commit()


async def create_task_run(task_id: str) -> int:
    if task_id not in TASK_DEFINITIONS:
        raise ValueError("未知任务")

    async with async_session() as db:
        run = TaskRun(task_id=task_id, status="queued", started_at=datetime.utcnow())
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


async def run_task_by_run_id(task_id: str, run_id: int):
    if task_id not in TASK_DEFINITIONS:
        raise ValueError("未知任务")

    started_at = datetime.utcnow()
    async with async_session() as db:
        run = await db.get(TaskRun, run_id)
        if not run or run.task_id != task_id:
            raise ValueError("运行记录不存在")

        run.status = "running"
        run.started_at = started_at
        db.add(run)
        await db.commit()

        try:
            task_func: Callable[[Any], Awaitable[None]] = TASK_DEFINITIONS[task_id]["func"]
            await task_func(db)
            run.status = "success"
            run.message = "ok"
        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            logger.exception(f"任务执行失败: {task_id}")
        finally:
            finished_at = datetime.utcnow()
            run.finished_at = finished_at
            run.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
            db.add(run)
            await db.commit()


async def run_task(task_id: str) -> int:
    if task_id not in TASK_DEFINITIONS:
        raise ValueError("未知任务")
    run_id = await create_task_run(task_id)
    await run_task_by_run_id(task_id, run_id)
    return run_id


async def _scheduled_entry(task_id: str):
    await run_task(task_id)


async def apply_task_config(task_id: str):
    if task_id not in TASK_DEFINITIONS:
        raise ValueError("任务不存在")
    async with async_session() as db:
        result = await db.execute(select(TaskConfig).where(TaskConfig.task_id == task_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise ValueError("任务不存在")

    trigger = _build_trigger(cfg)
    scheduler.add_job(
        _scheduled_entry,
        args=[task_id],
        trigger=trigger,
        id=task_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    if cfg.enabled:
        scheduler.resume_job(task_id)
    else:
        scheduler.pause_job(task_id)


async def start_scheduler():
    await ensure_task_configs()
    async with async_session() as db:
        result = await db.execute(select(TaskConfig))
        configs = [c for c in result.scalars().all() if c.task_id in TASK_DEFINITIONS]

    for cfg in configs:
        trigger = _build_trigger(cfg)
        scheduler.add_job(
            _scheduled_entry,
            args=[cfg.task_id],
            trigger=trigger,
            id=cfg.task_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )

    if not scheduler.running:
        scheduler.start()
        logger.info("定时任务调度器已启动")
    else:
        logger.info("定时任务调度器已刷新")

    for cfg in configs:
        if cfg.enabled:
            scheduler.resume_job(cfg.task_id)
        else:
            scheduler.pause_job(cfg.task_id)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("定时任务调度器已停止")
