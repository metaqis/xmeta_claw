"""定时任务调度"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from app.crawler.archive_crawler import crawl_archives
from app.crawler.archive_id_backfill import (
    backfill_archives_by_id_desc,
    get_max_numeric_archive_id,
    refresh_archives_around_max_id,
)
from app.crawler.calendar_archive_backfill import backfill_archives_for_calendar_range
from app.crawler.calendar_crawler import crawl_calendar_for_date, crawl_calendar_range, crawl_calendar_backward_until_no_data
from app.crawler.ip_uid_backfill import backfill_ip_source_uid
from app.crawler.launch_detail_crawler import crawl_all_missing_details
from app.crawler.jingtan_sku_homepage_detail_crawler import (
    crawl_jingtan_sku_homepage_details,
    crawl_jingtan_sku_homepage_details_desc_backfill,
    crawl_jingtan_sku_details_from_id_list,
    get_detail_numeric_sku_id_bounds,
)
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


async def task_crawl_recent_calendar_pipeline(db, run_id: int):
    logger.info("定时任务: 同步今明日日历链路")
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


async def task_sync_archives(db, run_id: int):
    logger.info("定时任务: 同步藏品库")
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
    await _log_run(db, run_id, "info", "开始藏品ID补齐: 15000 -> 10000")

    async def _on_progress(scanned: int, created: int, total: int, skipped: int, errors: int):
        await _log_run(
            db, run_id, "info",
            f"藏品ID补齐进度: 扫描 {scanned}/{total} 新增 {created} 跳过 {skipped} 失败 {errors}",
        )

    async def _on_error(archive_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"藏品 {archive_id} 请求失败: {error_msg}")

    scanned, created = await backfill_archives_by_id_desc(
        db,
        start_id=15000,
        stop_id=10000,
        platform_id=741,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(db, run_id, "info", f"藏品ID补齐完成: 扫描 {scanned} 新增 {created}")


async def task_archive_id_refresh_near_max(db, run_id: int):
    max_id = await get_max_numeric_archive_id(db)
    if max_id is None:
        await _log_run(db, run_id, "info", "无可用藏品ID，跳过")
        return
    await _log_run(db, run_id, "info", f"开始藏品ID邻域刷新: 围绕 {max_id} 前后各100")

    async def _on_progress(scanned: int, updated: int, failed: int, total: int):
        if scanned % 20 == 0 or scanned == total:
            await _log_run(
                db,
                run_id,
                "info",
                f"邻域刷新进度: 扫描 {scanned}/{total} 更新 {updated} 失败 {failed}",
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
    await _log_run(db, run_id, "info", f"邻域刷新完成: 扫描 {scanned} 更新 {updated} 失败 {failed}")


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


async def task_crawl_jingtan_sku_details(db, run_id: int):
    logger.info("定时任务: 鲸探藏品详情")
    await _log_run(db, run_id, "info", "开始爬取鲸探藏品详情")

    async def _on_progress(processed: int, upserted: int, failed: int, total: int):
        if processed % 20 == 0 or processed == total:
            await _log_run(
                db,
                run_id,
                "info",
                f"sku detail 进度: {processed}/{total} 入库 {upserted} 失败 {failed}",
            )

    async def _on_error(sku_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"sku detail 失败: sku_id={sku_id} {error_msg}")

    processed, upserted, failed = await crawl_jingtan_sku_homepage_details(
        db,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(
        db,
        run_id,
        "info",
        f"爬取完成: 处理 {processed} 入库 {upserted} 失败 {failed}",
    )


async def task_crawl_jingtan_sku_details_descending_backfill(db, run_id: int):
    logger.info("定时任务: 鲸探藏品详情倒序回填")
    max_sku_id, min_sku_id = await get_detail_numeric_sku_id_bounds(db)
    if max_sku_id is None or min_sku_id is None:
        await _log_run(db, run_id, "info", "详细表中无可用 sku_id，跳过倒序回填")
        return
    await _log_run(
        db,
        run_id,
        "info",
        f"开始倒序回填鲸探藏品详情（详细表最大ID -> 最小ID）: max_id={max_sku_id} min_id={min_sku_id}",
    )

    async def _on_progress(scanned: int, inserted: int, skipped: int, failed: int, current: int):
        if scanned % 20 == 0:
            await _log_run(
                db,
                run_id,
                "info",
                f"sku detail backfill: 扫描 {scanned} 新增 {inserted} 跳过 {skipped} 失败 {failed} 当前 {current}",
            )

    async def _on_error(sku_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"sku detail backfill 失败: sku_id={sku_id} {error_msg}")

    scanned, inserted, skipped, failed, skipped_sku_ids, failed_sku_ids = await crawl_jingtan_sku_homepage_details_desc_backfill(
        db,
        start_sku_id=max_sku_id,
        stop_sku_id=min_sku_id,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(
        db,
        run_id,
        "info",
        f"回填完成: 扫描 {scanned} 新增 {inserted} 跳过 {skipped} 失败 {failed}",
    )
    await _log_run(
        db,
        run_id,
        "info",
        f"skipped_sku_ids: {json.dumps(skipped_sku_ids, ensure_ascii=False)}",
    )
    await _log_run(
        db,
        run_id,
        "info",
        f"failed_sku_ids: {json.dumps(failed_sku_ids, ensure_ascii=False)}",
    )


_ID_LIST_FILE = Path(__file__).parent.parent.parent.parent / "third_goods_ids.txt"


async def task_crawl_jingtan_sku_details_from_idlist(db, run_id: int):
    logger.info("定时任务: 鲸探藏品详情(ID列表补齐)")

    if not _ID_LIST_FILE.exists():
        await _log_run(db, run_id, "error", f"ID列表文件不存在: {_ID_LIST_FILE}")
        return

    raw_ids = _ID_LIST_FILE.read_text(encoding="utf-8").splitlines()
    sku_ids = list(dict.fromkeys(line.strip() for line in raw_ids if line.strip().isdigit()))
    await _log_run(db, run_id, "info", f"读取 ID 列表: 共 {len(sku_ids)} 条（去重后）")

    async def _on_progress(scanned: int, inserted: int, skipped: int, failed: int, total: int):
        if scanned % 50 == 0 or scanned == total:
            await _log_run(
                db,
                run_id,
                "info",
                f"ID列表补齐进度: {scanned}/{total} 入库 {inserted} 跳过 {skipped} 失败 {failed}",
            )

    async def _on_error(sku_id: str, error_msg: str):
        await _log_run(db, run_id, "error", f"sku detail 失败: sku_id={sku_id} {error_msg}")

    total, inserted, skipped, failed = await crawl_jingtan_sku_details_from_id_list(
        db,
        sku_ids=sku_ids,
        on_progress=_on_progress,
        on_error=_on_error,
    )
    await _log_run(
        db,
        run_id,
        "info",
        f"ID列表补齐完成: 总计 {total} 入库 {inserted} 跳过 {skipped} 失败 {failed}",
    )


TASK_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "crawl_calendar": {
        "name": "今明日日历链路",
        "description": "抓取今日与明日日历，并补齐发行详情和关联藏品",
        "default_schedule_type": "interval",
        "default_interval_seconds": 60 * 60,
        "func": task_crawl_recent_calendar_pipeline,
    },
    "crawl_details": {
        "name": "发行详情补齐",
        "description": "补齐缺少 LaunchDetail 的发行记录",
        "default_schedule_type": "interval",
        "default_interval_seconds": 60 * 60,
        "func": task_crawl_details,
    },
    "crawl_archives": {
        "name": "藏品库同步",
        "description": "分页同步藏品列表，并按需补齐类型与 IP 信息",
        "default_schedule_type": "interval",
        "default_interval_seconds": 6 * 60 * 60,
        "func": task_sync_archives,
    },
    "full_crawl": {
        "name": "全量回扫链路",
        "description": "从 today+7 向前回扫日历，直到连续15天无数据，再补详情、关联藏品和藏品库",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_full_crawl,
    },
    "recent_7d_crawl": {
        "name": "近7天重跑链路",
        "description": "重跑近7天日历，并补齐详情、关联藏品和藏品库",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_recent_7d_crawl,
    },
    "archive_id_backfill": {
        "name": "藏品ID倒序补齐",
        "description": "从 archive_id=15000 向下补齐到 10000，并跳过已存在与 miss 记录",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_archive_id_backfill,
    },
    "archive_id_refresh_near_max": {
        "name": "最大ID邻域刷新",
        "description": "围绕当前最大 archive_id 前后各100重新拉取并强制更新",
        "default_schedule_type": "interval",
        "default_interval_seconds": 6 * 60 * 60,
        "default_enabled": False,
        "func": task_archive_id_refresh_near_max,
    },
    "ip_uid_backfill": {
        "name": "IP source_uid补齐",
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
        "name": "鲸探 SKU Wiki 同步",
        "description": "分页抓取 AntFans SKU Wiki 列表并更新本地 wiki 表",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_crawl_jingtan_sku_wiki,
    },
    "crawl_jingtan_sku_details": {
        "name": "鲸探 SKU 详情同步",
        "description": "遍历 wiki 中的 sku_id，只补齐详情表里缺失的记录，并同步 wiki 表",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_crawl_jingtan_sku_details,
    },
    "crawl_jingtan_sku_details_backfill": {
        "name": "鲸探 SKU 倒序回填",
        "description": "从详细表中的最大 sku_id 向下扫描到最小 sku_id，只补齐详情表中缺失的记录；详情优先入库，wiki 表尽力同步",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_crawl_jingtan_sku_details_descending_backfill,
    },
    "crawl_jingtan_sku_details_from_idlist": {
        "name": "鲸探 SKU ID列表补齐",
        "description": "从 third_goods_ids.txt 读取 sku_id，只补齐详情表中不存在的记录，并同步 wiki 表",
        "default_schedule_type": "interval",
        "default_interval_seconds": 24 * 60 * 60,
        "default_enabled": False,
        "func": task_crawl_jingtan_sku_details_from_idlist,
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
