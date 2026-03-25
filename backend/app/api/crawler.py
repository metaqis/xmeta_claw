"""管理爬虫的 API 接口"""
import asyncio

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel

from app.database.db import async_session
from app.api.auth import require_admin
from app.crawler.calendar_archive_backfill import backfill_archives_for_calendar_range
from app.crawler.calendar_crawler import crawl_calendar_for_date
from app.scheduler.tasks import create_task_run, run_task_by_run_id

router = APIRouter(prefix="/crawler", tags=["爬虫管理"])


class CrawlResponse(BaseModel):
    message: str
    status: str = "started"
    run_id: int | None = None


async def _trigger_task(task_id: str) -> int:
    run_id = await create_task_run(task_id)
    asyncio.create_task(run_task_by_run_id(task_id, run_id))
    return run_id


@router.post("/full", response_model=CrawlResponse)
async def start_full_crawl(
    _admin=Depends(require_admin),
):
    """启动统一任务体系中的全量回扫链路"""
    run_id = await _trigger_task("full_crawl")
    return CrawlResponse(message="全量回扫链路任务已触发", run_id=run_id)


@router.post("/calendar/{date}", response_model=CrawlResponse)
async def crawl_date(
    date: str,
    bg: BackgroundTasks,
    _admin=Depends(require_admin),
):
    """爬取指定日期的日历"""
    async def _task():
        async with async_session() as db:
            await crawl_calendar_for_date(db, date)
            await backfill_archives_for_calendar_range(db, date, date)

    bg.add_task(_task)
    return CrawlResponse(message=f"日历爬取已启动: {date}")


@router.post("/jingtan/sku-wiki", response_model=CrawlResponse)
async def crawl_jingtan_sku_wiki_full(
    _admin=Depends(require_admin),
):
    run_id = await _trigger_task("crawl_jingtan_sku_wiki")
    return CrawlResponse(message="鲸探 SKU Wiki 同步任务已触发", run_id=run_id)
