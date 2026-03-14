"""发行日历爬虫（第一阶段：日历基础数据 + 详情合并落库）"""
import json
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import IP, LaunchCalendar, LaunchDetail, Platform


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _extract_records(resp: dict) -> Tuple[list[dict], Optional[int]]:
    data = resp.get("data")
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        records = data.get("list") or data.get("data") or []
        pages = data.get("pages")
        return records if isinstance(records, list) else [], pages if isinstance(pages, int) else None
    return [], None


async def crawl_calendar_for_date(db: AsyncSession, date_str: str):
    page = 1
    page_size = 50
    inserted = 0

    while True:
        resp = await crawler_client.post_safe(
            "/h5/news/launchCalendar/list",
            {"pageNum": page, "pageSize": page_size, "date": date_str, "search": ""},
        )
        if not resp:
            break

        records, pages = _extract_records(resp)
        if not records:
            break

        for item in records:
            did_insert = await _upsert_calendar_from_list_item(db, item)
            if did_insert:
                inserted += 1

        if pages is not None:
            if page >= pages:
                break
            page += 1
            continue

        if len(records) < page_size:
            break
        page += 1

    await db.commit()
    logger.info(f"日历 {date_str}: 新增 {inserted} 条")
    return inserted


async def _upsert_calendar_from_list_item(db: AsyncSession, item: dict) -> bool:
    source_id = str(item.get("id") or "")
    if not source_id:
        return False

    existing_result = await db.execute(
        select(LaunchCalendar).where(LaunchCalendar.source_id == source_id)
    )
    existing = existing_result.scalar_one_or_none()

    platform_id, ip_id = await _ensure_platform_ip(db, item)

    if existing:
        if existing.platform_id is None and platform_id is not None:
            existing.platform_id = platform_id
        if existing.ip_id is None and ip_id is not None:
            existing.ip_id = ip_id

        detail_result = await db.execute(
            select(LaunchDetail).where(LaunchDetail.launch_id == existing.id)
        )
        if not detail_result.scalar_one_or_none():
            await _ensure_launch_detail(db, existing.id, source_id)
        return False

    calendar = LaunchCalendar(
        name=item.get("name") or "",
        sell_time=_parse_datetime(item.get("sellTime")),
        price=item.get("amount"),
        count=item.get("count"),
        platform_id=platform_id,
        ip_id=ip_id,
        img=item.get("img"),
        priority_purchase_num=item.get("priorityPurchaseNum") or 0,
        is_priority_purchase=bool(item.get("isPriorityPurchase")),
        source_id=source_id,
    )
    db.add(calendar)
    await db.flush()
    await _ensure_launch_detail(db, calendar.id, source_id)
    return True


async def _ensure_platform_ip(db: AsyncSession, item: dict) -> Tuple[Optional[int], Optional[int]]:
    platform_id = None
    platform_api_id = item.get("platformId")
    platform_name = item.get("platformName")
    platform_icon = item.get("platformImg")

    if platform_api_id or platform_name:
        platform = await _get_or_create_platform(db, platform_api_id, platform_name, platform_icon)
        platform_id = platform.id

    ip_id = None
    ip_name = item.get("ipName")
    ip_avatar = item.get("ipAvatar")
    if ip_name:
        ip_obj = await _get_or_create_ip(db, ip_name, ip_avatar, platform_id)
        ip_id = ip_obj.id

    return platform_id, ip_id


async def _ensure_launch_detail(db: AsyncSession, launch_id: int, source_id: str):
    resp = await crawler_client.post_safe(
        "/h5/news/launchCalendar/detailed",
        {"id": int(source_id) if source_id.isdigit() else source_id},
    )
    if not resp:
        return
    detail_data = resp.get("data") or {}
    if not isinstance(detail_data, dict) or not detail_data:
        return

    detail = LaunchDetail(
        launch_id=launch_id,
        priority_purchase_time=_parse_datetime(detail_data.get("priorityPurchaseTime")),
        context_condition=detail_data.get("contextCondition"),
        status=str(detail_data.get("status")) if detail_data.get("status") is not None else None,
        raw_json=json.dumps(detail_data, ensure_ascii=False),
    )
    db.add(detail)
    await db.flush()


async def _get_or_create_platform(
    db: AsyncSession,
    platform_api_id: Any,
    name: Any,
    icon: Any,
) -> Platform:
    platform = None
    if platform_api_id is not None:
        try:
            platform_id = int(platform_api_id)
            result = await db.execute(select(Platform).where(Platform.id == platform_id))
            platform = result.scalar_one_or_none()
            if not platform and name:
                platform = Platform(id=platform_id, name=str(name), icon=icon)
                db.add(platform)
                await db.flush()
                return platform
        except (ValueError, TypeError):
            platform = None

    if name:
        result = await db.execute(select(Platform).where(Platform.name == str(name)))
        platform = result.scalar_one_or_none()
        if platform:
            if icon and not platform.icon:
                platform.icon = icon
            return platform

    platform = Platform(name=str(name or "未知平台"), icon=icon)
    db.add(platform)
    await db.flush()
    return platform


async def _get_or_create_ip(
    db: AsyncSession,
    ip_name: Any,
    ip_avatar: Any,
    platform_id: Optional[int],
) -> IP:
    name = str(ip_name or "未知IP")
    result = await db.execute(
        select(IP).where(IP.ip_name == name, IP.platform_id == platform_id)
    )
    ip_obj = result.scalar_one_or_none()
    if ip_obj:
        if ip_avatar and not ip_obj.ip_avatar:
            ip_obj.ip_avatar = ip_avatar
        return ip_obj
    ip_obj = IP(ip_name=name, ip_avatar=ip_avatar, platform_id=platform_id)
    db.add(ip_obj)
    await db.flush()
    return ip_obj


async def crawl_calendar_range(db: AsyncSession, start_date: str, end_date: str):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    current = start
    total = 0

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        count = await crawl_calendar_for_date(db, date_str)
        total += count
        current += timedelta(days=1)

    logger.info(f"日历范围爬取完成: {start_date} ~ {end_date}, 共新增 {total} 条")
    return total
