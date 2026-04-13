"""定时任务调度"""
import asyncio
import inspect
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from app.crawler.archive_id_backfill import (
    backfill_archives_by_id_desc,
    get_max_numeric_archive_id,
    refresh_archives_around_max_id,
)
from app.crawler.calendar_archive_backfill import backfill_archives_for_calendar_range
from app.crawler.calendar_crawler import crawl_calendar_for_date_stats, crawl_calendar_range
from app.crawler.ip_crawler import refresh_ip_profiles
from app.crawler.ip_uid_backfill import backfill_ip_source_uid
from app.crawler.jingtan_sku_homepage_detail_crawler import (
    crawl_jingtan_sku_homepage_details,
    crawl_jingtan_sku_details_around_max_id,
)
from app.crawler.jingtan_sku_wiki_crawler import crawl_jingtan_sku_wiki
from app.crawler.market_snapshot_crawler import run_market_snapshot
from app.article.service import generate_article
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


async def task_today_calendar_update(db, run_id: int):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await _log_run(db, run_id, "info", f"开始今日日历强制更新: {today}")

    fetched, upserted = await crawl_calendar_for_date_stats(db, today, force_update=True)
    await _log_run(db, run_id, "info", f"日历拉取完成: 拉取 {fetched} 新增/更新 {upserted}")

    async def _on_progress(done: int, total: int):
        await _log_run(db, run_id, "info", f"关联藏品补齐进度: {done}/{total}")

    await backfill_archives_for_calendar_range(db, today, today, on_progress=_on_progress)
    await _log_run(db, run_id, "info", "关联藏品补齐完成")


async def task_forward_10d_calendar_update(db, run_id: int):
    today = datetime.now(timezone.utc)
    start = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=10)).strftime("%Y-%m-%d")
    await _log_run(db, run_id, "info", f"开始未来10天日历更新: {start} ~ {end}")

    async def _on_day(date_str: str, count: int):
        await _log_run(db, run_id, "info", f"日历 {date_str}: 新增/更新 {count}")

    await crawl_calendar_range(db, start, end, on_day_done=_on_day, force_update=True)
    await _log_run(db, run_id, "info", "未来10天日历更新完成")


async def task_archive_refresh_near_max(db, run_id: int):
    max_id = await get_max_numeric_archive_id(db)
    if max_id is None:
        await _log_run(db, run_id, "info", "无可用藏品ID，跳过")
        return
    await _log_run(db, run_id, "info", f"开始藏品ID邂域刷新: 围绕 {max_id} 前后各04100")

    async def _on_progress(scanned: int, updated: int, failed: int, total: int):
        if scanned % 20 == 0 or scanned == total:
            await _log_run(
                db, run_id, "info",
                f"邂域刷新进度: 扫描 {scanned}/{total} 更新 {updated} 失败 {failed}",
            )

    async def _on_error(archive_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"藏品 {archive_id} 刷新失败: {error_msg}")

    scanned, updated, failed = await refresh_archives_around_max_id(
        db,
        around_count=100,
        platform_id=741,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(db, run_id, "info", f"邂域刷新完成: 扫描 {scanned} 更新 {updated} 失败 {failed}")


async def task_archive_explore_new(db, run_id: int, params: dict | None = None):
    """向上探索当前 max_id 之后的新藏品 ID"""
    max_id = await get_max_numeric_archive_id(db)
    if max_id is None:
        await _log_run(db, run_id, "info", "无可用藏品ID，跳过")
        return
    explore_count = int((params or {}).get("explore_count", 300))
    explore_count = max(10, min(explore_count, 5000))
    start_id = max_id + explore_count
    stop_id = max_id + 1
    await _log_run(db, run_id, "info", f"开始探索新藏品ID: 当前max={max_id} 扫描范围 [{stop_id}, {start_id}]")

    async def _on_progress(scanned: int, created: int, total: int, skipped: int, errors: int):
        if scanned % 50 == 0 or scanned == total:
            await _log_run(
                db, run_id, "info",
                f"探索进度: {scanned}/{total} 新增 {created} 跳过 {skipped} 失败 {errors}",
            )

    async def _on_error(archive_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"藏品 {archive_id} 失败: {error_msg}")

    scanned, created = await backfill_archives_by_id_desc(
        db,
        start_id=start_id,
        stop_id=stop_id,
        platform_id=741,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(db, run_id, "info", f"新ID探索完成: 扫描 {scanned} 新增 {created}")


async def task_ip_uid_backfill(db, run_id: int):
    await _log_run(db, run_id, "info", "开始补齐 IP source_uid")

    async def _on_progress(processed: int, updated: int, total: int):
        await _log_run(db, run_id, "info", f"IP source_uid 补齐进度: {processed}/{total} 已更新 {updated}")

    processed, updated = await backfill_ip_source_uid(db, on_progress=_on_progress)
    await _log_run(db, run_id, "info", f"IP source_uid 补齐完成: 处理 {processed} 更新 {updated}")


async def task_ip_profile_refresh(db, run_id: int):
    await _log_run(db, run_id, "info", "开始刷新 IP 资料 (粉丝数/头像/简介)")

    async def _on_progress(processed: int, updated: int, total: int):
        await _log_run(db, run_id, "info", f"IP 资料刷新进度: {processed}/{total} 已更新 {updated}")

    processed, updated = await refresh_ip_profiles(db, on_progress=_on_progress)
    await _log_run(db, run_id, "info", f"IP 资料刷新完成: 处理 {processed} 更新 {updated}")


async def task_import_planes(db, run_id: int):
    await _log_run(db, run_id, "info", "开始导入版块")
    count = await import_planes_to_db(db)
    await _log_run(db, run_id, "info", f"版块导入完成: {count}")


async def task_jingtan_wiki_incremental(db, run_id: int):
    await _log_run(db, run_id, "info", "开始鲸探 wiki 增量更新 (每类最多2页)")

    async def _on_page(page: int, fetched: int, upserted: int):
        await _log_run(db, run_id, "info", f"wiki page {page}: 拉取 {fetched} 入库 {upserted}")

    fetched, upserted = await crawl_jingtan_sku_wiki(db, max_pages=2, on_page_done=_on_page)
    await _log_run(db, run_id, "info", f"wiki 更新完成: 拉取 {fetched} 入库 {upserted}")

    await _log_run(db, run_id, "info", "开始补齐缺失的 sku 详情")

    async def _on_detail_progress(processed: int, upserted_d: int, failed: int, total: int):
        if processed % 50 == 0 or processed == total:
            await _log_run(
                db, run_id, "info",
                f"detail 补齐进度: {processed}/{total} 入库 {upserted_d} 失败 {failed}",
            )

    async def _on_detail_error(sku_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"detail 失败: sku_id={sku_id} {error_msg}")

    d_processed, d_upserted, d_failed = await crawl_jingtan_sku_homepage_details(
        db,
        only_missing=True,
        on_progress=_on_detail_progress,
        on_error=_on_detail_error,
    )
    await _log_run(
        db, run_id, "info",
        f"detail 补齐完成: 处理 {d_processed} 入库 {d_upserted} 失败 {d_failed}",
    )


async def task_jingtan_detail_around_max(db, run_id: int):
    await _log_run(db, run_id, "info", "开始鲸探 SKU 详情邂域补齐 (当前最大ID 前后各04500)")

    async def _on_progress(scanned: int, inserted: int, skipped: int, failed: int, total: int):
        if scanned % 100 == 0 or scanned == total:
            await _log_run(
                db, run_id, "info",
                f"邂域补齐进度: {scanned}/{total} 入库 {inserted} 跳过 {skipped} 失败 {failed}",
            )

    async def _on_error(sku_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"sku_id={sku_id} {error_msg}")

    total, inserted, skipped, failed = await crawl_jingtan_sku_details_around_max_id(
        db,
        spread_backward=200,
        spread_forward=100,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(
        db, run_id, "info",
        f"邂域补齐完成: 总计 {total} 入库 {inserted} 跳过 {skipped} 失败 {failed}",
    )


async def task_article_daily(db, run_id: int):
    await _log_run(db, run_id, "info", "开始生成每日文章")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    article = await generate_article(db, "daily", today)
    await _log_run(db, run_id, "info", f"每日文章生成完成: id={article.id} title={article.title}")


async def task_article_weekly(db, run_id: int):
    await _log_run(db, run_id, "info", "开始生成每周文章")
    article = await generate_article(db, "weekly")
    await _log_run(db, run_id, "info", f"每周文章生成完成: id={article.id} title={article.title}")


async def task_article_monthly(db, run_id: int):
    await _log_run(db, run_id, "info", "开始生成每月文章")
    now = datetime.now(timezone.utc)
    # 生成上个月的月报
    if now.month == 1:
        y, m = now.year - 1, 12
    else:
        y, m = now.year, now.month - 1
    article = await generate_article(db, "monthly", f"{y}-{m:02d}-01")
    await _log_run(db, run_id, "info", f"每月文章生成完成: id={article.id} title={article.title}")


async def task_market_snapshot(db, run_id: int):
    await _log_run(db, run_id, "info", "开始市场快照抓取 (板块/IP/热门藏品)")

    async def _on_log(msg: str):
        await _log_run(db, run_id, "info", msg)

    result = await run_market_snapshot(db, on_log=_on_log)
    await _log_run(
        db, run_id, "info",
        f"市场快照完成: 板块={result['plane_count']} IP={result['ip_count']} 藏品={result['archive_count']}",
    )


TASK_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "today_calendar_update": {
        "name": "今日日历强制更新",
        "description": "拉取今日日历并强制更新已有条目（名称/价格/数量/优先购等），同时补齐关联藏品",
        "default_schedule_type": "interval",
        "default_interval_seconds": 3 * 60 * 60,
        "func": task_today_calendar_update,
    },
    "forward_10d_calendar_update": {
        "name": "未来10天日历更新",
        "description": "拉取 today+1 到 today+10 的日历并强制更新已有条目",
        "default_schedule_type": "interval",
        "default_interval_seconds": 6 * 60 * 60,
        "func": task_forward_10d_calendar_update,
    },
    "archive_id_refresh_near_max": {
        "name": "xmeta 藏品最大ID邂域刷新",
        "description": "围绕当前最大 archive_id 前后各04100 重新拉取并强制更新",
        "default_schedule_type": "interval",
        "default_interval_seconds": 6 * 60 * 60,
        "func": task_archive_refresh_near_max,
    },
    "archive_id_explore_new": {
        "name": "xmeta 新藏品ID向上探索",
        "description": "从当前最大 archive_id+1 向上扫描 N 个ID，发现并入库新发行藏品",
        "default_schedule_type": "interval",
        "default_interval_seconds": 2 * 60 * 60,
        "func": task_archive_explore_new,
        "params_schema": [
            {"key": "explore_count", "label": "扫描数量", "type": "int", "default": 300, "min": 10, "max": 5000},
        ],
    },
    "ip_uid_backfill": {
        "name": "IP source_uid 补齐",
        "description": "通过关联藏品详情补齐 IP 的 source_uid",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "func": task_ip_uid_backfill,
    },
    "ip_profile_refresh": {
        "name": "IP 资料刷新",
        "description": "重新拉取所有已知 source_uid 的 IP 主页，更新粉丝数、头像、简介",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "func": task_ip_profile_refresh,
    },
    "import_planes_daily": {
        "name": "版块每日导入",
        "description": "每日导入并更新版块列表",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "func": task_import_planes,
    },
    "jingtan_wiki_incremental": {
        "name": "鲸探 SKU Wiki 增量更新",
        "description": "每个分类最多拉取2页，更新 wiki 表；对无详情记录的 sku_id 同步补齐详情",
        "default_schedule_type": "interval",
        "default_interval_seconds": 3 * 60 * 60,
        "func": task_jingtan_wiki_incremental,
    },
    "jingtan_detail_around_max": {
        "name": "鲸探 SKU 详情邂域补齐",
        "description": "在当前最大 sku_id 前后各04500 范围内，只补齐详情表中缺失的记录",
        "default_schedule_type": "interval",
        "default_interval_seconds": 48 * 60 * 60,
        "func": task_jingtan_detail_around_max,
    },
    "article_daily": {
        "name": "每日文章自动生成",
        "description": "每天自动生成数藏日报文章（基于当日发行日历数据）",
        "default_schedule_type": "cron",
        "default_cron": "30 6 * * *",
        "default_enabled": False,
        "func": task_article_daily,
    },
    "article_weekly": {
        "name": "每周文章自动生成",
        "description": "每周一自动生成数藏周报（基于过去一周数据）",
        "default_schedule_type": "cron",
        "default_cron": "0 10 * * 1",
        "default_enabled": False,
        "func": task_article_weekly,
    },
    "article_monthly": {
        "name": "每月文章自动生成",
        "description": "每月1日自动生成数藏月报（基于上一个月数据）",
        "default_schedule_type": "cron",
        "default_cron": "0 10 1 * *",
        "default_enabled": False,
        "func": task_article_monthly,
    },
    "market_snapshot_daily": {
        "name": "市场每日快照",
        "description": "每天 23:50 抓取板块统计、IP 排行、热门藏品数据，写入快照表供日报分析使用",
        "default_schedule_type": "cron",
        "default_cron": "50 23 * * *",
        "default_enabled": True,
        "func": task_market_snapshot,
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
        run = TaskRun(task_id=task_id, status="queued", started_at=datetime.now(timezone.utc))
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

        now = datetime.now(timezone.utc)
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


async def run_task_by_run_id(task_id: str, run_id: int, params: dict | None = None):
    if task_id not in TASK_DEFINITIONS:
        raise ValueError("未知任务")

    started_at = datetime.now(timezone.utc)
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
            run.finished_at = datetime.now(timezone.utc)
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
            sig = inspect.signature(task_func)
            if "params" in sig.parameters:
                await task_func(db, run_id, params=params)
            else:
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
            finished_at = datetime.now(timezone.utc)
            run.finished_at = finished_at
            run.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
            db.add(run)
            await db.commit()


async def run_task(task_id: str, params: dict | None = None) -> int:
    if task_id not in TASK_DEFINITIONS:
        raise ValueError("未知任务")
    run_id = await create_task_run(task_id)
    await run_task_by_run_id(task_id, run_id, params=params)
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

