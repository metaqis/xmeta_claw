"""藏品数据爬虫"""
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.archive_detail_service import (
    archive_needs_detail_sync,
    fetch_archive_detail,
    upsert_archive_from_detail,
)
from app.crawler.client import crawler_client
from app.crawler.platform_ip_service import find_ip_id_by_name, find_platform_id_by_name
from app.database.models import Archive


PLATFORM_ID_JINGTAN = "741"  # 鲸探平台ID


async def crawl_archives(db: AsyncSession, platform_id: str = PLATFORM_ID_JINGTAN):
    """爬取藏品列表"""
    page = 1
    page_size = 20
    total_saved = 0

    while True:
        data = await crawler_client.post_safe(
            "/h5/goods/archive",
            {
                "archiveId": "",
                "platformId": platform_id,
                "page": page,
                "pageSize": page_size,
                "sellStatus": 1,
            },
        )
        if not data:
            break

        records = data.get("data", {}).get("list", [])
        if not records:
            break

        for item in records:
            await _save_archive(db, item)
            total_saved += 1

        total_items = data.get("data", {}).get("total", 0)
        if page * page_size >= total_items:
            break
        page += 1

    await db.commit()
    logger.info(f"藏品爬取完成: 共 {total_saved} 条")
    return total_saved


async def _save_archive(db: AsyncSession, item: dict):
    archive_id = str(item.get("archiveId", ""))
    if not archive_id:
        return

    result = await db.execute(select(Archive).where(Archive.archive_id == archive_id))
    existing = result.scalar_one_or_none()

    platform_info = item.get("platform") or {}
    platform_id = await find_platform_id_by_name(db, platform_info.get("name"))

    ip_info = item.get("ip") or {}
    ip_id = await find_ip_id_by_name(db, ip_info.get("ipName"))

    issue_time = None
    issue_time_str = item.get("issueTime")
    if issue_time_str:
        try:
            issue_time = datetime.strptime(issue_time_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass

    detail = None
    if await archive_needs_detail_sync(db, existing):
        detail = await fetch_archive_detail(archive_id, platform_id or PLATFORM_ID_JINGTAN)
        if detail:
            await upsert_archive_from_detail(
                db,
                detail,
                {
                    "archive_id": archive_id,
                    "platform_id": platform_id,
                    "platform_name": platform_info.get("name"),
                    "ip_name": ip_info.get("ipName"),
                    "ip_avatar": ip_info.get("ipAvatar"),
                },
            )
            result = await db.execute(select(Archive).where(Archive.archive_id == archive_id))
            existing = result.scalar_one_or_none()

    if existing:
        existing.archive_name = item.get("archiveName", existing.archive_name)
        existing.is_open_auction = bool(item.get("isOpenAuction"))
        existing.is_open_want_buy = bool(item.get("isOpenWantBuy"))
        existing.img = item.get("img") or existing.img
        if ip_id is not None and existing.ip_id is None:
            existing.ip_id = ip_id
        if existing.platform_id is None and platform_id is not None:
            existing.platform_id = platform_id
        if existing.issue_time is None and issue_time is not None:
            existing.issue_time = issue_time
        existing.updated_at = datetime.utcnow()
    else:
        archive = Archive(
            archive_id=archive_id,
            archive_name=item.get("archiveName", ""),
            platform_id=platform_id,
            ip_id=ip_id,
            issue_time=issue_time,
            archive_description=item.get("archiveDescription"),
            is_open_auction=bool(item.get("isOpenAuction")),
            is_open_want_buy=bool(item.get("isOpenWantBuy")),
            img=item.get("img"),
        )
        db.add(archive)
