"""管理爬虫的 API 接口"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from loguru import logger

from app.database.db import async_session
from app.api.auth import require_admin
from app.crawler.calendar_archive_backfill import backfill_archives_for_calendar_range
from app.crawler.calendar_crawler import crawl_calendar_range, crawl_calendar_for_date
from app.crawler.launch_detail_crawler import crawl_all_missing_details
from app.crawler.archive_crawler import crawl_archives

router = APIRouter(prefix="/crawler", tags=["爬虫管理"])


class CrawlResponse(BaseModel):
    message: str
    status: str = "started"


async def _run_full_crawl():
    """后台执行完整爬取"""
    async with async_session() as db:
        try:
            today = datetime.utcnow()
            start = (today - timedelta(days=730)).strftime("%Y-%m-%d")
            end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
            logger.info(f"开始完整爬取: {start} ~ {end}")
            await crawl_calendar_range(db, start, end)
            await crawl_all_missing_details(db)
            await backfill_archives_for_calendar_range(db, start, end)
            await crawl_archives(db)
            logger.info("完整爬取完成")
        except Exception as e:
            logger.error(f"完整爬取失败: {e}")


@router.post("/full", response_model=CrawlResponse)
async def start_full_crawl(
    bg: BackgroundTasks,
    _admin=Depends(require_admin),
):
    """启动完整数据爬取（后台执行）"""
    bg.add_task(_run_full_crawl)
    return CrawlResponse(message="完整爬取任务已启动")


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
