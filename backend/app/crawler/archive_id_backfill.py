from typing import Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.calendar_archive_backfill import _fetch_archive_detail, _upsert_archive_from_detail
from app.database.models import Archive


async def get_max_numeric_archive_id(db: AsyncSession) -> Optional[int]:
    result = await db.execute(
        select(func.max(cast(Archive.archive_id, Integer))).where(Archive.archive_id.op("~")("^[0-9]+$"))
    )
    value = result.scalar_one_or_none()
    return int(value) if value is not None else None


async def backfill_archives_by_id_desc(
    db: AsyncSession,
    start_id: int,
    stop_id: int = 15000,
    platform_id: int = 741,
    on_progress: Callable[[int, int, int], Awaitable[None]] | None = None,
) -> Tuple[int, int]:
    if start_id < stop_id:
        return 0, 0

    scanned = 0
    created = 0
    total = start_id - stop_id + 1
    if on_progress is not None:
        await on_progress(scanned, created, total)

    for aid in range(start_id, stop_id - 1, -1):
        scanned += 1
        existing = await db.get(Archive, str(aid))
        if existing is not None:
            if on_progress is not None and (scanned % 200 == 0 or scanned == total):
                await on_progress(scanned, created, total)
            continue

        detail = await _fetch_archive_detail(str(aid), platform_id)
        if not detail:
            if on_progress is not None and (scanned % 200 == 0 or scanned == total):
                await on_progress(scanned, created, total)
            continue

        await _upsert_archive_from_detail(db, detail, {"archive_id": str(aid), "platform_id": platform_id})
        created += 1

        if created % 20 == 0:
            await db.commit()

        if on_progress is not None and (scanned % 200 == 0 or scanned == total):
            await on_progress(scanned, created, total)

    await db.commit()
    logger.info(f"藏品ID补齐完成: 扫描 {scanned}，新增 {created}")
    return scanned, created

