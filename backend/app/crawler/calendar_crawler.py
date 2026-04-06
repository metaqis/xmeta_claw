"""发行日历爬虫（第一阶段：日历基础数据 + 详情合并落库）"""
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.crawler.launch_detail_service import save_launch_detail
from app.crawler.platform_ip_service import ensure_platform_and_ip_from_calendar_item
from app.database.models import LaunchCalendar


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


async def crawl_calendar_for_date_stats(
    db: AsyncSession, date_str: str, force_update: bool = False
) -> Tuple[int, int]:
    page = 1
    page_size = 50
    inserted = 0
    fetched = 0

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

        fetched += len(records)
        for item in records:
            did_insert = await _upsert_calendar_from_list_item(db, item, force_update=force_update)
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
    logger.info(f"日历 {date_str}: 新增/更新 {inserted} 条")
    return fetched, inserted


async def crawl_calendar_for_date(db: AsyncSession, date_str: str, force_update: bool = False) -> int:
    _, inserted = await crawl_calendar_for_date_stats(db, date_str, force_update=force_update)
    return inserted


async def _upsert_calendar_from_list_item(
    db: AsyncSession, item: dict, force_update: bool = False
) -> bool:
    source_id = str(item.get("id") or "")
    if not source_id:
        return False

    existing_result = await db.execute(
        select(LaunchCalendar).where(LaunchCalendar.source_id == source_id)
    )
    existing = existing_result.scalar_one_or_none()

    platform_id, ip_id = await ensure_platform_and_ip_from_calendar_item(db, item)

    if existing:
        if existing.platform_id is None and platform_id is not None:
            existing.platform_id = platform_id
        if existing.ip_id is None and ip_id is not None:
            existing.ip_id = ip_id
        if force_update:
            existing.name = item.get("name") or ""
            existing.sell_time = _parse_datetime(item.get("sellTime"))
            existing.price = item.get("amount")
            existing.count = item.get("count")
            existing.img = item.get("img")
            existing.priority_purchase_num = item.get("priorityPurchaseNum") or 0
            existing.is_priority_purchase = bool(item.get("isPriorityPurchase"))
        await save_launch_detail(db, existing.id, source_id, skip_existing=not force_update)
        return force_update

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
    await save_launch_detail(db, calendar.id, source_id, skip_existing=False)
    return True


async def crawl_calendar_range(
    db: AsyncSession,
    start_date: str,
    end_date: str,
    on_day_done: Callable[[str, int], Awaitable[None]] | None = None,
    force_update: bool = False,
):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    current = start
    total = 0

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        _, count = await crawl_calendar_for_date_stats(db, date_str, force_update=force_update)
        total += count
        if on_day_done is not None:
            await on_day_done(date_str, count)
        current += timedelta(days=1)

    logger.info(f"日历范围爬取完成: {start_date} ~ {end_date}, 共新增/更新 {total} 条")
    return total


async def crawl_calendar_backward_until_no_data(
    db: AsyncSession,
    start_date: str,
    max_no_data_days: int = 15,
    on_day_done: Callable[[str, int, int, int], Awaitable[None]] | None = None,
) -> Tuple[str, str, int]:
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end_date = start_date
    no_data_streak = 0
    total_inserted = 0

    while True:
        date_str = current.strftime("%Y-%m-%d")
        fetched, inserted = await crawl_calendar_for_date_stats(db, date_str)
        total_inserted += inserted

        if fetched <= 0:
            no_data_streak += 1
        else:
            no_data_streak = 0

        if on_day_done is not None:
            await on_day_done(date_str, fetched, inserted, no_data_streak)

        if no_data_streak >= max_no_data_days:
            oldest = (current + timedelta(days=max_no_data_days - 1)).strftime("%Y-%m-%d")
            logger.info(f"连续 {max_no_data_days} 天无数据，停止向前爬取，最早有效日期约为 {oldest}")
            return oldest, end_date, total_inserted

        current -= timedelta(days=1)
