"""发行日历爬虫"""
import json
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import LaunchCalendar, Platform, IP


async def crawl_calendar_for_date(db: AsyncSession, date_str: str):
    """爬取某一天的发行日历"""
    page = 1
    page_size = 50
    total_saved = 0

    while True:
        data = await crawler_client.post_safe(
            "/h5/news/launchCalendar/list",
            {"pageNum": page, "pageSize": page_size, "date": date_str, "search": ""},
        )
        if not data:
            break

        records = data.get("data", {}).get("list", [])
        if not records:
            break

        for item in records:
            await _save_calendar_item(db, item)
            total_saved += 1

        total_pages = data.get("data", {}).get("pages", 1)
        if page >= total_pages:
            break
        page += 1

    await db.commit()
    logger.info(f"日历 {date_str}: 保存 {total_saved} 条")
    return total_saved


async def _save_calendar_item(db: AsyncSession, item: dict):
    source_id = str(item.get("id", ""))
    if not source_id:
        return

    # 检查是否已存在
    existing = await db.execute(
        select(LaunchCalendar).where(LaunchCalendar.source_id == source_id)
    )
    if existing.scalar_one_or_none():
        return

    # 平台
    platform_id = None
    platform_info = item.get("platform") or {}
    if platform_info.get("id"):
        platform = await _get_or_create_platform(db, platform_info)
        platform_id = platform.id

    # IP
    ip_id = None
    ip_info = item.get("ip") or {}
    if ip_info.get("ipName"):
        ip_obj = await _get_or_create_ip(db, ip_info, platform_id)
        ip_id = ip_obj.id

    sell_time = None
    sell_time_str = item.get("sellTime")
    if sell_time_str:
        try:
            sell_time = datetime.strptime(sell_time_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass

    calendar = LaunchCalendar(
        name=item.get("name", ""),
        sell_time=sell_time,
        price=item.get("price"),
        count=item.get("count"),
        platform_id=platform_id,
        ip_id=ip_id,
        img=item.get("img"),
        priority_purchase_num=item.get("priorityPurchaseNum", 0),
        is_priority_purchase=bool(item.get("isPriorityPurchase")),
        source_id=source_id,
    )
    db.add(calendar)


async def _get_or_create_platform(db: AsyncSession, info: dict) -> Platform:
    name = info.get("name", "未知平台")
    result = await db.execute(select(Platform).where(Platform.name == name))
    platform = result.scalar_one_or_none()
    if platform:
        return platform
    platform = Platform(name=name, icon=info.get("icon"))
    db.add(platform)
    await db.flush()
    return platform


async def _get_or_create_ip(db: AsyncSession, info: dict, platform_id: int | None) -> IP:
    ip_name = info.get("ipName", "未知IP")
    result = await db.execute(
        select(IP).where(IP.ip_name == ip_name, IP.platform_id == platform_id)
    )
    ip_obj = result.scalar_one_or_none()
    if ip_obj:
        return ip_obj
    ip_obj = IP(ip_name=ip_name, ip_avatar=info.get("ipAvatar"), platform_id=platform_id)
    db.add(ip_obj)
    await db.flush()
    return ip_obj


async def crawl_calendar_range(db: AsyncSession, start_date: str, end_date: str):
    """遍历日期范围爬取日历"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    current = start
    total = 0

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        count = await crawl_calendar_for_date(db, date_str)
        total += count
        current += timedelta(days=1)

    logger.info(f"日历范围爬取完成: {start_date} ~ {end_date}, 共 {total} 条")
    return total
