import json
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.crawler.ip_crawler import get_or_create_ip_by_source_uid
from app.database.models import Archive, IP, LaunchCalendar, LaunchDetail, Platform


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _collect_associated_archive_refs(raw_json: Optional[str]) -> list[dict]:
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except Exception:
        return []

    refs: list[dict] = []

    def _collect(items: Any):
        if not isinstance(items, list):
            return
        for x in items:
            if not isinstance(x, dict):
                continue
            aid = x.get("associatedArchiveId")
            if aid is None:
                continue
            refs.append(
                {
                    "archive_id": str(aid),
                    "platform_id": x.get("platformId"),
                    "platform_name": x.get("platformName"),
                    "platform_img": x.get("platformImg"),
                    "ip_name": x.get("ipName"),
                    "ip_avatar": x.get("ipAvatar"),
                }
            )

    _collect(data.get("containArchiveList"))
    _collect(data.get("associationArchiveList"))

    seen = set()
    unique: list[dict] = []
    for r in refs:
        key = (r.get("archive_id"), r.get("platform_id"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


async def _get_or_create_platform(
    db: AsyncSession,
    platform_api_id: Any,
    name: Any,
    icon: Any,
) -> Platform:
    platform = None
    if platform_api_id is not None:
        try:
            pid = int(platform_api_id)
            result = await db.execute(select(Platform).where(Platform.id == pid))
            platform = result.scalar_one_or_none()
            if platform:
                if icon and not platform.icon:
                    platform.icon = icon
                if name and not platform.name:
                    platform.name = str(name)
                return platform
            if name:
                platform = Platform(id=pid, name=str(name), icon=icon)
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
) -> Optional[IP]:
    if not ip_name:
        return None
    name = str(ip_name)
    result = await db.execute(select(IP).where(IP.ip_name == name, IP.platform_id == platform_id))
    ip_obj = result.scalar_one_or_none()
    if ip_obj:
        if ip_avatar and not ip_obj.ip_avatar:
            ip_obj.ip_avatar = ip_avatar
        return ip_obj
    ip_obj = IP(ip_name=name, ip_avatar=ip_avatar, platform_id=platform_id)
    db.add(ip_obj)
    await db.flush()
    return ip_obj


async def _fetch_archive_detail(archive_id: str, platform_id: Optional[Any]) -> Optional[dict]:
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
    if isinstance(data, dict):
        return data
    return None


async def _upsert_archive_from_detail(
    db: AsyncSession,
    detail: dict,
    ref: dict,
):
    archive_id = str(detail.get("archiveId") or ref.get("archive_id") or "")
    if not archive_id:
        return

    platform = await _get_or_create_platform(
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
        ip_obj = await _get_or_create_ip(
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
        existing.platform_id = existing.platform_id or platform.id
        if ip_obj and existing.ip_id is None:
            existing.ip_id = ip_obj.id
        existing.issue_time = existing.issue_time or issue_time
        existing.archive_description = detail.get("archiveDescription") or existing.archive_description
        existing.archive_type = archive_type_value or existing.archive_type
        if existing.total_goods_count is None and total_goods_count_value is not None:
            existing.total_goods_count = total_goods_count_value
        existing.is_open_auction = bool(detail.get("isOpenAuction")) if detail.get("isOpenAuction") is not None else existing.is_open_auction
        existing.is_open_want_buy = bool(detail.get("isOpenWantBuy")) if detail.get("isOpenWantBuy") is not None else existing.is_open_want_buy
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


async def backfill_archives_for_calendar_range(
    db: AsyncSession,
    start_date: str,
    end_date: str,
) -> int:
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    result = await db.execute(
        select(LaunchDetail.raw_json)
        .join(LaunchCalendar, LaunchCalendar.id == LaunchDetail.launch_id)
        .where(LaunchCalendar.sell_time.between(start, end))
        .where(LaunchDetail.raw_json.isnot(None))
    )
    raw_list = [row[0] for row in result.all()]

    refs: list[dict] = []
    for raw in raw_list:
        refs.extend(_collect_associated_archive_refs(raw))

    if not refs:
        return 0

    wanted_ids = {r["archive_id"] for r in refs if r.get("archive_id")}
    if not wanted_ids:
        return 0

    created_or_updated = 0
    for r in refs:
        archive_id = r.get("archive_id")
        if not archive_id:
            continue

        existing_result = await db.execute(select(Archive).where(Archive.archive_id == archive_id))
        existing_archive = existing_result.scalar_one_or_none()
        should_process = existing_archive is None
        if existing_archive is not None:
            ip_obj = None
            if existing_archive.ip_id is not None:
                ip_obj = await db.get(IP, existing_archive.ip_id)
            needs_ip = (ip_obj is None) or (ip_obj.source_uid is None) or (not ip_obj.description)
            needs_type = (not existing_archive.archive_type) or (
                isinstance(existing_archive.archive_type, str) and existing_archive.archive_type.isdigit()
            )
            needs_count = existing_archive.total_goods_count is None
            should_process = needs_ip or needs_type or needs_count
        if not should_process:
            continue

        detail = await _fetch_archive_detail(archive_id, r.get("platform_id"))
        if not detail:
            continue
        await _upsert_archive_from_detail(db, detail, r)
        created_or_updated += 1

    await db.commit()
    logger.info(f"日历关联藏品补齐完成: 新增/更新 {created_or_updated} 条")
    return created_or_updated
