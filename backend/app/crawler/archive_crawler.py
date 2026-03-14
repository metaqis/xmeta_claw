"""藏品数据爬虫"""
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.crawler.ip_crawler import get_or_create_ip_by_source_uid
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

    async def _fetch_detail():
        data = await crawler_client.post_safe(
            "/h5/goods/archive",
            {
                "archiveId": archive_id,
                "platformId": PLATFORM_ID_JINGTAN,
                "active": "6",
                "page": 1,
                "pageSize": 20,
                "sellStatus": 1,
                "dealType": "",
                "goodsType": "",
                "isPayBond": "",
                "startTime": "",
                "endTime": "",
                "fancyNumberType": "",
            },
        )
        if not data:
            return None
        detail = data.get("data")
        return detail if isinstance(detail, dict) else None

    def _extract_type_name(detail: dict | None) -> str | None:
        if not detail:
            return None
        plane_code_json = detail.get("planeCodeJson")
        if isinstance(plane_code_json, list) and plane_code_json:
            first = plane_code_json[0]
            if isinstance(first, dict) and first.get("name"):
                return str(first["name"])
        return None

    def _extract_total_count(detail: dict | None) -> int | None:
        if not detail:
            return None
        value = detail.get("totalGoodsCount")
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return None

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

    detail = None
    type_name = None
    total_count = None
    should_fetch_type = (not existing) or (not existing.archive_type) or (
        isinstance(existing.archive_type, str) and existing.archive_type.isdigit()
    )

    should_fetch_ip = False
    if existing and existing.ip_id is not None:
        ip_obj = await db.get(IP, existing.ip_id)
        should_fetch_ip = ip_obj is not None and (ip_obj.source_uid is None or not ip_obj.description or ip_obj.fans_count is None)
    if should_fetch_type or should_fetch_ip:
        detail = await _fetch_detail()
        type_name = _extract_type_name(detail)
        total_count = _extract_total_count(detail)

    if detail and (not existing or existing.ip_id is None):
        source_uid = detail.get("ipId")
        try:
            source_uid_value = int(source_uid) if source_uid is not None else None
        except (ValueError, TypeError):
            source_uid_value = None
        if source_uid_value is not None:
            ip_profile = await get_or_create_ip_by_source_uid(
                db,
                source_uid=source_uid_value,
                platform_id=platform_id,
                from_type=1,
                fallback_name=detail.get("ipName"),
                fallback_avatar=detail.get("ipAvatar"),
            )
            if ip_profile:
                ip_id = ip_profile.id
    if detail and existing and existing.ip_id is not None:
        source_uid = detail.get("ipId")
        try:
            source_uid_value = int(source_uid) if source_uid is not None else None
        except (ValueError, TypeError):
            source_uid_value = None
        if source_uid_value is not None:
            await get_or_create_ip_by_source_uid(
                db,
                source_uid=source_uid_value,
                platform_id=platform_id,
                from_type=1,
                fallback_name=detail.get("ipName"),
                fallback_avatar=detail.get("ipAvatar"),
            )

    if existing:
        existing.archive_name = item.get("archiveName", existing.archive_name)
        existing.is_open_auction = bool(item.get("isOpenAuction"))
        existing.is_open_want_buy = bool(item.get("isOpenWantBuy"))
        existing.img = item.get("img") or existing.img
        if type_name:
            existing.archive_type = type_name
        if existing.total_goods_count is None and total_count is not None:
            existing.total_goods_count = total_count
        if ip_id is not None and existing.ip_id is None:
            existing.ip_id = ip_id
        existing.updated_at = datetime.utcnow()
    else:
        archive = Archive(
            archive_id=archive_id,
            archive_name=item.get("archiveName", ""),
            total_goods_count=total_count,
            platform_id=platform_id,
            ip_id=ip_id,
            issue_time=issue_time,
            archive_description=item.get("archiveDescription"),
            archive_type=type_name,
            is_open_auction=bool(item.get("isOpenAuction")),
            is_open_want_buy=bool(item.get("isOpenWantBuy")),
            img=item.get("img"),
        )
        db.add(archive)
