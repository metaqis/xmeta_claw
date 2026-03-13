"""管理爬虫的 API 接口"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from loguru import logger

from app.database.db import async_session
from app.api.auth import require_admin
from app.crawler.calendar_crawler import crawl_calendar_range, crawl_calendar_for_date
from app.crawler.launch_detail_crawler import crawl_all_missing_details
from app.crawler.archive_crawler import crawl_archives
from app.crawler.market_crawler import update_market_data

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
            end = (today + timedelta(days=30)).strftime("%Y-%m-%d")
            logger.info(f"开始完整爬取: {start} ~ {end}")
            await crawl_calendar_range(db, start, end)
            await crawl_all_missing_details(db)
            await crawl_archives(db)
            await update_market_data(db)
            logger.info("完整爬取完成")
        except Exception as e:
            logger.error(f"完整爬取失败: {e}")


async def _run_market_update():
    async with async_session() as db:
        try:
            await update_market_data(db)
        except Exception as e:
            logger.error(f"市场更新失败: {e}")


@router.post("/full", response_model=CrawlResponse)
async def start_full_crawl(
    bg: BackgroundTasks,
    _admin=Depends(require_admin),
):
    """启动完整数据爬取（后台执行）"""
    bg.add_task(_run_full_crawl)
    return CrawlResponse(message="完整爬取任务已启动")


@router.post("/market", response_model=CrawlResponse)
async def start_market_update(
    bg: BackgroundTasks,
    _admin=Depends(require_admin),
):
    """手动触发市场数据更新"""
    bg.add_task(_run_market_update)
    return CrawlResponse(message="市场数据更新已启动")


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

    bg.add_task(_task)
    return CrawlResponse(message=f"日历爬取已启动: {date}")
