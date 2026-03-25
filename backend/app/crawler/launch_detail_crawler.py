"""发行详情爬虫"""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LaunchCalendar, LaunchDetail
from app.crawler.launch_detail_service import save_launch_detail


async def crawl_launch_detail(db: AsyncSession, launch_id: int, source_id: str):
    """爬取单个发行详情"""
    did_save = await save_launch_detail(db, launch_id, source_id, skip_existing=True)
    if did_save:
        logger.debug(f"详情已保存: launch_id={launch_id}")


async def crawl_all_missing_details(db: AsyncSession):
    """爬取所有缺少详情的发行记录"""
    result = await db.execute(
        select(LaunchCalendar)
        .outerjoin(LaunchDetail, LaunchCalendar.id == LaunchDetail.launch_id)
        .where(LaunchDetail.id.is_(None))
        .where(LaunchCalendar.source_id.isnot(None))
    )
    calendars = result.scalars().all()
    logger.info(f"需要爬取详情: {len(calendars)} 条")

    for cal in calendars:
        await crawl_launch_detail(db, cal.id, cal.source_id)

    await db.commit()
    logger.info("发行详情爬取完成")
