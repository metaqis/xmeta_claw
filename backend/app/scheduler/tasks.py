"""定时任务调度"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from app.crawler.archive_crawler import crawl_archives
from app.crawler.archive_id_backfill import backfill_archives_by_id_desc, get_max_numeric_archive_id
from app.crawler.calendar_archive_backfill import backfill_archives_for_calendar_range
from app.crawler.calendar_crawler import crawl_calendar_for_date, crawl_calendar_range, crawl_calendar_backward_until_no_data
from app.crawler.ip_uid_backfill import backfill_ip_source_uid
from app.crawler.launch_detail_crawler import crawl_all_missing_details
from app.crawler.jingtan_sku_wiki_crawler import crawl_jingtan_sku_wiki
from app.database.db import async_session
from app.database.models import TaskConfig, TaskRun, TaskRunLog
from app.services.plane_importer import import_planes_to_db

scheduler = AsyncIOScheduler()
_RUNNING_TASKS: Dict[int, asyncio.Task] = {}


async def _log_run(db, run_id: int, level: str, message: str):
    log = TaskRunLog(run_id=run_id, level=level, message=message)
    db.add(log)
    run = await db.get(TaskRun, run_id)
    if run:
        run.message = message
        db.add(run)
    await db.commit()


async def task_crawl_today_calendar(db, run_id: int):
    logger.info("定时任务: 爬取今日日历")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    await _log_run(db, run_id, "info", f"开始爬取日历: {today} ~ {tomorrow}")
    await crawl_calendar_for_date(db, today)
    await _log_run(db, run_id, "info", f"日历完成: {today}")
    await crawl_calendar_for_date(db, tomorrow)
    await _log_run(db, run_id, "info", f"日历完成: {tomorrow}")
    await crawl_all_missing_details(db)
    await _log_run(db, run_id, "info", "发行详情补全完成")
    async def _on_progress(done: int, total: int):
        await _log_run(db, run_id, "info", f"关联藏品补齐进度: {done}/{total}")

    await backfill_archives_for_calendar_range(db, today, tomorrow, on_progress=_on_progress)
    await _log_run(db, run_id, "info", "关联藏品补齐完成")


async def task_crawl_details(db, run_id: int):
    logger.info("定时任务: 补全发行详情")
    await _log_run(db, run_id, "info", "开始补全发行详情")
    await crawl_all_missing_details(db)
    await _log_run(db, run_id, "info", "补全发行详情完成")


async def task_crawl_archives(db, run_id: int):
    logger.info("定时任务: 爬取藏品列表")
    await _log_run(db, run_id, "info", "开始更新藏品库")
    await crawl_archives(db)
    await _log_run(db, run_id, "info", "更新藏品库完成")


async def task_full_crawl(db, run_id: int):
    end = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
    await _log_run(db, run_id, "info", f"开始全量爬取: 从 {end} 往前，连续15天无数据停止")

    async def _on_day(date_str: str, fetched: int, inserted: int, streak: int):
        await _log_run(db, run_id, "info", f"日历 {date_str}: 拉取 {fetched} 新增 {inserted} 连续无数据 {streak}")

    start, end, _ = await crawl_calendar_backward_until_no_data(
        db,
        start_date=end,
        max_no_data_days=15,
        on_day_done=_on_day,
    )
    await _log_run(db, run_id, "info", f"日历倒序爬取完成: {start} ~ {end}")
    await crawl_all_missing_details(db)
    await _log_run(db, run_id, "info", "发行详情补全完成")
    async def _on_progress(done: int, total: int):
        await _log_run(db, run_id, "info", f"关联藏品补齐进度: {done}/{total}")

    await backfill_archives_for_calendar_range(db, start, end, on_progress=_on_progress)
    await _log_run(db, run_id, "info", "关联藏品补齐完成")
    await crawl_archives(db)
    await _log_run(db, run_id, "info", "藏品库更新完成")


async def task_recent_7d_crawl(db, run_id: int):
    today = datetime.utcnow()
    start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    await _log_run(db, run_id, "info", f"开始近7天爬取: {start} ~ {end}")

    async def _on_day(date_str: str, inserted: int):
        await _log_run(db, run_id, "info", f"日历 {date_str}: 新增 {inserted}")

    await crawl_calendar_range(db, start, end, on_day_done=_on_day)
    await _log_run(db, run_id, "info", "日历范围爬取完成")
    await crawl_all_missing_details(db)
    await _log_run(db, run_id, "info", "发行详情补全完成")
    async def _on_progress(done: int, total: int):
        await _log_run(db, run_id, "info", f"关联藏品补齐进度: {done}/{total}")

    await backfill_archives_for_calendar_range(db, start, end, on_progress=_on_progress)
    await _log_run(db, run_id, "info", "关联藏品补齐完成")
    await crawl_archives(db)
    await _log_run(db, run_id, "info", "藏品库更新完成")


async def task_archive_id_backfill(db, run_id: int):
    max_id = await get_max_numeric_archive_id(db)
    if max_id is None:
        await _log_run(db, run_id, "info", "无可用藏品ID，跳过")
        return
    await _log_run(db, run_id, "info", f"开始藏品ID补齐: {max_id} -> 15000")

    async def _on_progress(scanned: int, created: int, total: int, skipped: int, errors: int):
        await _log_run(
            db, run_id, "info",
            f"藏品ID补齐进度: 扫描 {scanned}/{total} 新增 {created} 跳过 {skipped} 失败 {errors}",
        )

    async def _on_error(archive_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"藏品 {archive_id} 请求失败: {error_msg}")

    scanned, created = await backfill_archives_by_id_desc(
        db,
        start_id=max_id,
        stop_id=15000,
        platform_id=741,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(db, run_id, "info", f"藏品ID补齐完成: 扫描 {scanned} 新增 {created}")


async def task_ip_uid_backfill(db, run_id: int):
    await _log_run(db, run_id, "info", "开始补齐 IP source_uid")

    async def _on_progress(processed: int, updated: int, total: int):
        await _log_run(db, run_id, "info", f"IP source_uid 补齐进度: {processed}/{total} 已更新 {updated}")

    processed, updated = await backfill_ip_source_uid(db, on_progress=_on_progress)
    await _log_run(db, run_id, "info", f"IP source_uid 补齐完成: 处理 {processed} 更新 {updated}")


async def task_import_planes(db, run_id: int):
    await _log_run(db, run_id, "info", "开始导入板块")
    count = await import_planes_to_db(db)
    await _log_run(db, run_id, "info", f"板块导入完成: {count}")


async def task_crawl_jingtan_sku_wiki(db, run_id: int):
    logger.info("定时任务: 鲸探藏品库(sku wiki)")
    await _log_run(db, run_id, "info", "开始爬取鲸探藏品库(sku wiki)")

    async def _on_page(page: int, fetched: int, upserted: int):
        await _log_run(db, run_id, "info", f"sku wiki page {page}: 拉取 {fetched} 入库 {upserted}")

    fetched, upserted = await crawl_jingtan_sku_wiki(db, on_page_done=_on_page)
    await _log_run(db, run_id, "info", f"爬取完成: 拉取 {fetched} 入库 {upserted}")


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
    "full_crawl": {
        "name": "全量爬取",
        "description": "按时间范围全量爬取日历、详情、藏品并补齐关联",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_full_crawl,
    },
    "recent_7d_crawl": {
        "name": "近7天爬取",
        "description": "重跑近7天日历、详情并补齐关联藏品",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_recent_7d_crawl,
    },
    "archive_id_backfill": {
        "name": "藏品ID补齐",
        "description": "从数据库最大 archiveId 往前补齐到 15000（跳过已存在）",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_archive_id_backfill,
    },
    "ip_uid_backfill": {
        "name": "IP UID补齐",
        "description": "通过关联藏品详情补齐 IP 的 source_uid",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_ip_uid_backfill,
    },
    "import_planes_weekly": {
        "name": "板块周导入",
        "description": "每周导入并更新板块列表",
        "default_schedule_type": "cron",
        "default_cron": "0 3 * * 1",
        "func": task_import_planes,
    },
    "crawl_jingtan_sku_wiki": {
        "name": "鲸探藏品库",
        "description": "爬取并更新鲸探藏品库(sku wiki)",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_crawl_jingtan_sku_wiki,
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
                enabled=meta.get("default_enabled", True),
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


async def cancel_task_run(task_id: str, run_id: int) -> bool:
    async with async_session() as db:
        run = await db.get(TaskRun, run_id)
        if not run or run.task_id != task_id:
            return False
        if run.status in ("success", "failed", "cancelled"):
            return False

        now = datetime.utcnow()
        if run.status == "queued":
            run.status = "cancelled"
            run.finished_at = now
            run.duration_ms = int((now - run.started_at).total_seconds() * 1000) if run.started_at else None
            run.message = "已停止"
            db.add(TaskRunLog(run_id=run_id, level="warn", message="任务已停止"))
            db.add(run)
            await db.commit()
            return True

        run.status = "cancelling"
        run.message = "停止中"
        db.add(TaskRunLog(run_id=run_id, level="warn", message="请求停止任务"))
        db.add(run)
        await db.commit()

    task = _RUNNING_TASKS.get(run_id)
    if task and not task.done():
        task.cancel()
        return True
    return True


async def run_task_by_run_id(task_id: str, run_id: int):
    if task_id not in TASK_DEFINITIONS:
        raise ValueError("未知任务")

    started_at = datetime.utcnow()
    async with async_session() as db:
        current_task = asyncio.current_task()
        if current_task:
            _RUNNING_TASKS[run_id] = current_task
        run = await db.get(TaskRun, run_id)
        if not run or run.task_id != task_id:
            raise ValueError("运行记录不存在")

        if run.status == "cancelled":
            _RUNNING_TASKS.pop(run_id, None)
            return
        if run.status == "cancelling":
            run.status = "cancelled"
            run.finished_at = datetime.utcnow()
            run.duration_ms = int((run.finished_at - started_at).total_seconds() * 1000)
            run.message = "已停止"
            db.add(TaskRunLog(run_id=run_id, level="warn", message="任务已停止"))
            db.add(run)
            await db.commit()
            _RUNNING_TASKS.pop(run_id, None)
            return

        run.status = "running"
        run.started_at = started_at
        db.add(run)
        await db.commit()

        try:
            task_func: Callable[[Any, int], Awaitable[None]] = TASK_DEFINITIONS[task_id]["func"]
            await task_func(db, run_id)
            run.status = "success"
            if not run.message:
                run.message = "success"
        except asyncio.CancelledError:
            run.status = "cancelled"
            run.message = "已停止"
            db.add(run)
            await _log_run(db, run_id, "warn", "任务已停止")
        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            await _log_run(db, run_id, "error", f"失败: {run.error}")
            logger.exception(f"任务执行失败: {task_id}")
        finally:
            _RUNNING_TASKS.pop(run_id, None)
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
