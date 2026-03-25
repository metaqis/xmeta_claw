"""藏品详情共享能力"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.crawler.ip_crawler import get_or_create_ip_by_source_uid
from app.crawler.platform_ip_service import get_or_create_ip, get_or_create_platform
from app.database.models import Archive, IP


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


async def fetch_archive_detail(archive_id: str, platform_id: Optional[Any]) -> Optional[dict]:
    payload = {
        "archiveId": archive_id,
        "platformId": str(platform_id) if platform_id is not None else "741",
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
    }
    resp = await crawler_client.post_safe("/h5/goods/archive", payload)
    if not resp:
        return None
    data = resp.get("data")
    if not isinstance(data, dict):
        return None
    real_id = data.get("archiveId")
    if real_id is None or str(real_id) != str(archive_id):
        return None
    return data


async def archive_needs_detail_sync(
    db: AsyncSession,
    existing_archive: Optional[Archive],
) -> bool:
    if existing_archive is None:
        return True

    ip_obj = None
    if existing_archive.ip_id is not None:
        ip_obj = await db.get(IP, existing_archive.ip_id)
    needs_ip = (ip_obj is None) or (ip_obj.source_uid is None) or (not ip_obj.description) or (ip_obj.fans_count is None)
    needs_type = (not existing_archive.archive_type) or (
        isinstance(existing_archive.archive_type, str) and existing_archive.archive_type.isdigit()
    )
    needs_count = existing_archive.total_goods_count is None
    return needs_ip or needs_type or needs_count


async def upsert_archive_from_detail(
    db: AsyncSession,
    detail: dict,
    ref: dict,
    force_update: bool = False,
):
    archive_id = str(detail.get("archiveId") or ref.get("archive_id") or "")
    if not archive_id:
        return

    platform = await get_or_create_platform(
        db,
        detail.get("platformId") or ref.get("platform_id"),
        detail.get("platformName") or ref.get("platform_name"),
        detail.get("platformIcon") or ref.get("platform_img"),
    )
    source_uid = detail.get("ipId")
    try:
        source_uid_value = int(source_uid) if source_uid is not None else None
    except (ValueError, TypeError):
        source_uid_value = None

    ip_obj = None
    if source_uid_value is not None:
        ip_obj = await get_or_create_ip_by_source_uid(
            db,
            source_uid=source_uid_value,
            platform_id=platform.id if platform else None,
            from_type=1,
            fallback_name=detail.get("ipName") or ref.get("ip_name"),
            fallback_avatar=detail.get("ipAvatar") or ref.get("ip_avatar"),
        )
    if ip_obj is None:
        ip_obj = await get_or_create_ip(
            db,
            detail.get("ipName") or ref.get("ip_name"),
            detail.get("ipAvatar") or ref.get("ip_avatar"),
            platform.id if platform else None,
        )

    issue_time = _parse_datetime(detail.get("issueTime"))
    images = detail.get("archiveImage")
    img = images[0] if isinstance(images, list) and images else None
    total_goods_count = detail.get("totalGoodsCount")
    try:
        total_goods_count_value = int(total_goods_count) if total_goods_count is not None else None
    except (ValueError, TypeError):
        total_goods_count_value = None
    archive_type_value = None
    plane_code_json = detail.get("planeCodeJson")
    if isinstance(plane_code_json, list) and plane_code_json:
        first = plane_code_json[0]
        if isinstance(first, dict) and first.get("name"):
            archive_type_value = str(first["name"])

    result = await db.execute(select(Archive).where(Archive.archive_id == archive_id))
    existing = result.scalar_one_or_none()
    if existing:
        existing.archive_name = detail.get("archiveName") or existing.archive_name
        if force_update and platform and platform.id is not None:
            existing.platform_id = platform.id
        else:
            existing.platform_id = existing.platform_id or platform.id
        if ip_obj and (force_update or existing.ip_id is None):
            existing.ip_id = ip_obj.id
        if force_update:
            if issue_time is not None:
                existing.issue_time = issue_time
        else:
            existing.issue_time = existing.issue_time or issue_time
        if force_update:
            if detail.get("archiveDescription") is not None:
                existing.archive_description = detail.get("archiveDescription")
        else:
            existing.archive_description = detail.get("archiveDescription") or existing.archive_description
        if force_update:
            if archive_type_value:
                existing.archive_type = archive_type_value
        else:
            existing.archive_type = archive_type_value or existing.archive_type
        if force_update:
            if total_goods_count_value is not None:
                existing.total_goods_count = total_goods_count_value
        elif existing.total_goods_count is None and total_goods_count_value is not None:
            existing.total_goods_count = total_goods_count_value
        existing.is_open_auction = bool(detail.get("isOpenAuction")) if detail.get("isOpenAuction") is not None else existing.is_open_auction
        existing.is_open_want_buy = bool(detail.get("isOpenWantBuy")) if detail.get("isOpenWantBuy") is not None else existing.is_open_want_buy
        if force_update:
            if img:
                existing.img = img
        else:
            existing.img = img or existing.img
        return

    archive = Archive(
        archive_id=archive_id,
        archive_name=detail.get("archiveName") or ref.get("archive_id") or "",
        total_goods_count=total_goods_count_value,
        platform_id=platform.id if platform else None,
        ip_id=ip_obj.id if ip_obj else None,
        issue_time=issue_time,
        archive_description=detail.get("archiveDescription"),
        archive_type=archive_type_value,
        is_open_auction=bool(detail.get("isOpenAuction")),
        is_open_want_buy=bool(detail.get("isOpenWantBuy")),
        img=img,
    )
    db.add(archive)
