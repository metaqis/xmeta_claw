"""定时任务调度"""
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.database.db import async_session
from app.crawler.calendar_crawler import crawl_calendar_for_date
from app.crawler.launch_detail_crawler import crawl_all_missing_details
from app.crawler.archive_crawler import crawl_archives
from app.crawler.market_crawler import update_market_data

scheduler = AsyncIOScheduler()


async def job_update_market():
    """每10分钟更新市场数据"""
    logger.info("定时任务: 更新市场数据")
    async with async_session() as db:
        try:
            await update_market_data(db)
        except Exception as e:
            logger.error(f"市场数据更新失败: {e}")


async def job_crawl_today_calendar():
    """每小时爬取今日和明日的日历"""
    logger.info("定时任务: 爬取今日日历")
    async with async_session() as db:
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
            await crawl_calendar_for_date(db, today)
            await crawl_calendar_for_date(db, tomorrow)
        except Exception as e:
            logger.error(f"日历爬取失败: {e}")


async def job_crawl_details():
    """每小时补全缺失的发行详情"""
    logger.info("定时任务: 补全发行详情")
    async with async_session() as db:
        try:
            await crawl_all_missing_details(db)
        except Exception as e:
            logger.error(f"详情爬取失败: {e}")


async def job_crawl_archives():
    """每6小时爬取藏品列表"""
    logger.info("定时任务: 爬取藏品列表")
    async with async_session() as db:
        try:
            await crawl_archives(db)
        except Exception as e:
            logger.error(f"藏品爬取失败: {e}")


def start_scheduler():
    """启动所有定时任务"""
    # 每10分钟更新市场数据
    scheduler.add_job(
        job_update_market,
        trigger=IntervalTrigger(minutes=10),
        id="update_market",
        replace_existing=True,
    )

    # 每小时爬取今日日历
    scheduler.add_job(
        job_crawl_today_calendar,
        trigger=IntervalTrigger(hours=1),
        id="crawl_calendar",
        replace_existing=True,
    )

    # 每小时补全详情
    scheduler.add_job(
        job_crawl_details,
        trigger=IntervalTrigger(hours=1),
        id="crawl_details",
        replace_existing=True,
    )

    # 每6小时爬取藏品
    scheduler.add_job(
        job_crawl_archives,
        trigger=IntervalTrigger(hours=6),
        id="crawl_archives",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("定时任务调度器已启动")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("定时任务调度器已停止")
