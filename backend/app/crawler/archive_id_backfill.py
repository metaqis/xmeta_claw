"""藏品ID倒序补齐，使用批量数据库查询优化性能"""
import asyncio
from typing import Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.calendar_archive_backfill import _fetch_archive_detail, _upsert_archive_from_detail
from app.database.models import Archive


BATCH_CHECK_SIZE = 500  # 每次批量检查的ID数量


async def get_max_numeric_archive_id(db: AsyncSession) -> Optional[int]:
    result = await db.execute(
        select(func.max(cast(Archive.archive_id, Integer))).where(Archive.archive_id.op("~")("^[0-9]+$"))
    )
    value = result.scalar_one_or_none()
    return int(value) if value is not None else None


async def _batch_check_existing(db: AsyncSession, id_list: list[str]) -> set[str]:
    """批量查询已存在的 archive_id 集合"""
    if not id_list:
        return set()
    result = await db.execute(
        select(Archive.archive_id).where(Archive.archive_id.in_(id_list))
    )
    return {row[0] for row in result.all()}


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

    # 按批次处理，每批先批量查库过滤已存在的
    current = start_id
    while current >= stop_id:
        batch_end = max(current - BATCH_CHECK_SIZE + 1, stop_id)
        batch_ids = [str(aid) for aid in range(current, batch_end - 1, -1)]
        batch_size = len(batch_ids)

        # 批量查询已存在的 ID
        existing_ids = await _batch_check_existing(db, batch_ids)
        missing_ids = [aid for aid in batch_ids if aid not in existing_ids]

        scanned += batch_size

        # 并发拉取缺失的藏品详情（受 client 信号量限制）
        async def _fetch_and_upsert(aid: str):
            detail = await _fetch_archive_detail(aid, platform_id)
            if detail:
                await _upsert_archive_from_detail(db, detail, {"archive_id": aid, "platform_id": platform_id})
                return True
            return False

        # 分小组并发拉取，避免一次并发过多
        chunk_size = 5
        for i in range(0, len(missing_ids), chunk_size):
            chunk = missing_ids[i:i + chunk_size]
            results = await asyncio.gather(
                *[_fetch_and_upsert(aid) for aid in chunk],
                return_exceptions=True,
            )
            for r in results:
                if r is True:
                    created += 1

        if created % 20 == 0 and created > 0:
            await db.commit()

        if on_progress is not None:
            await on_progress(scanned, created, total)

        current = batch_end - 1

    await db.commit()
    logger.info(f"藏品ID补齐完成: 扫描 {scanned}，新增 {created}")
    return scanned, created
