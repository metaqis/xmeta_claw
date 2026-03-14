"""发行详情爬虫"""
import json
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import LaunchCalendar, LaunchDetail


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


async def crawl_launch_detail(db: AsyncSession, launch_id: int, source_id: str):
    """爬取单个发行详情"""
    # 检查是否已存在
    existing = await db.execute(
        select(LaunchDetail).where(LaunchDetail.launch_id == launch_id)
    )
    if existing.scalar_one_or_none():
        return

    data = await crawler_client.post_safe(
        "/h5/news/launchCalendar/detailed",
        {"id": source_id},
    )
    if not data:
        return

    detail_data = data.get("data", {})
    if not detail_data:
        return

    detail = LaunchDetail(
        launch_id=launch_id,
        priority_purchase_time=_parse_datetime(detail_data.get("priorityPurchaseTime")),
        context_condition=detail_data.get("contextCondition"),
        status=str(detail_data.get("status")) if detail_data.get("status") is not None else None,
        raw_json=json.dumps(detail_data, ensure_ascii=False),
    )
    db.add(detail)
    await db.commit()
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

    logger.info("发行详情爬取完成")
