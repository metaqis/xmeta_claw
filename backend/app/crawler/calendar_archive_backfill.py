import json
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.archive_detail_service import (
    archive_needs_detail_sync,
    fetch_archive_detail,
    upsert_archive_from_detail,
)
from app.database.models import Archive, LaunchCalendar, LaunchDetail


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


async def backfill_archives_for_calendar_range(
    db: AsyncSession,
    start_date: str,
    end_date: str,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
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
    processed = 0
    total = len(refs)
    if on_progress is not None:
        await on_progress(0, total)
    for r in refs:
        archive_id = r.get("archive_id")
        if not archive_id:
            continue

        existing_result = await db.execute(select(Archive).where(Archive.archive_id == archive_id))
        existing_archive = existing_result.scalar_one_or_none()
        should_process = await archive_needs_detail_sync(db, existing_archive)
        if not should_process:
            processed += 1
            if on_progress is not None and (processed % 20 == 0 or processed == total):
                await on_progress(processed, total)
            continue

        detail = await fetch_archive_detail(archive_id, r.get("platform_id"))
        if not detail:
            processed += 1
            if on_progress is not None and (processed % 20 == 0 or processed == total):
                await on_progress(processed, total)
            continue
        await upsert_archive_from_detail(db, detail, r)
        created_or_updated += 1
        processed += 1
        if on_progress is not None and (processed % 20 == 0 or processed == total):
            await on_progress(processed, total)

    await db.commit()
    logger.info(f"日历关联藏品补齐完成: 新增/更新 {created_or_updated} 条")
    return created_or_updated
