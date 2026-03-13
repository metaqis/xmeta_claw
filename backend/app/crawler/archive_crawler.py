"""藏品数据爬虫"""
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import Archive, Platform, IP


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

    # 检查已存在则更新
    result = await db.execute(select(Archive).where(Archive.archive_id == archive_id))
    existing = result.scalar_one_or_none()

    # 平台
    platform_id = None
    platform_info = item.get("platform") or {}
    if platform_info.get("name"):
        plat_result = await db.execute(
            select(Platform).where(Platform.name == platform_info["name"])
        )
        plat = plat_result.scalar_one_or_none()
        if plat:
            platform_id = plat.id

    # IP
    ip_id = None
    ip_info = item.get("ip") or {}
    if ip_info.get("ipName"):
        ip_result = await db.execute(
            select(IP).where(IP.ip_name == ip_info["ipName"])
        )
        ip_obj = ip_result.scalar_one_or_none()
        if ip_obj:
            ip_id = ip_obj.id

    issue_time = None
    issue_time_str = item.get("issueTime")
    if issue_time_str:
        try:
            issue_time = datetime.strptime(issue_time_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass

    if existing:
        existing.archive_name = item.get("archiveName", existing.archive_name)
        existing.is_hot = bool(item.get("isHot"))
        existing.is_open_auction = bool(item.get("isOpenAuction"))
        existing.is_open_want_buy = bool(item.get("isOpenWantBuy"))
        existing.img = item.get("img") or existing.img
        existing.updated_at = datetime.utcnow()
    else:
        archive = Archive(
            archive_id=archive_id,
            archive_name=item.get("archiveName", ""),
            platform_id=platform_id,
            ip_id=ip_id,
            issue_time=issue_time,
            archive_description=item.get("archiveDescription"),
            archive_type=item.get("archiveType"),
            is_hot=bool(item.get("isHot")),
            is_open_auction=bool(item.get("isOpenAuction")),
            is_open_want_buy=bool(item.get("isOpenWantBuy")),
            img=item.get("img"),
        )
        db.add(archive)
