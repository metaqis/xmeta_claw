"""藏品ID倒序补齐，使用批量数据库查询优化性能"""
import asyncio
from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.calendar_archive_backfill import _fetch_archive_detail, _upsert_archive_from_detail
from app.database.models import Archive, ArchiveMiss


BATCH_CHECK_SIZE = 500  # 每次批量检查的ID数量


async def get_max_numeric_archive_id(db: AsyncSession) -> Optional[int]:
    result = await db.execute(
        select(func.max(cast(Archive.archive_id, Integer))).where(Archive.archive_id.op("~")("^[0-9]+$"))
    )
    value = result.scalar_one_or_none()
    return int(value) if value is not None else None


async def _batch_check_existing(db: AsyncSession, id_list: list[str]) -> set[str]:
    """批量查询已存在的 archive_id 集合（含已确认不存在的 miss 记录）"""
    if not id_list:
        return set()
    # 查已存在的藏品
    result = await db.execute(
        select(Archive.archive_id).where(Archive.archive_id.in_(id_list))
    )
    found = {row[0] for row in result.all()}
    # 查已确认不存在的 ID（避免重复请求）
    miss_result = await db.execute(
        select(ArchiveMiss.archive_id).where(ArchiveMiss.archive_id.in_(id_list))
    )
    found.update(row[0] for row in miss_result.all())
    return found


async def _record_misses(db: AsyncSession, miss_ids: list[str]):
    """批量记录 API 不存在的 archive_id"""
    if not miss_ids:
        return
    now = datetime.utcnow()
    for aid in miss_ids:
        existing = await db.get(ArchiveMiss, aid)
        if not existing:
            db.add(ArchiveMiss(archive_id=aid, checked_at=now))


async def _fetch_and_upsert(
    db: AsyncSession,
    aid: str,
    platform_id: int,
) -> Optional[bool]:
    """拉取单个藏品详情并入库，返回 True=新增, False=API无数据, None=出错"""
    detail = await _fetch_archive_detail(aid, platform_id)
    if detail:
        await _upsert_archive_from_detail(db, detail, {"archive_id": aid, "platform_id": platform_id})
        return True
    return False


async def backfill_archives_by_id_desc(
    db: AsyncSession,
    start_id: int,
    stop_id: int = 15000,
    platform_id: int = 741,
    on_progress: Callable[[int, int, int, int, int], Awaitable[None]] | None = None,
    on_error: Callable[[str, str], Awaitable[None]] | None = None,
) -> Tuple[int, int]:
    """
    on_progress(scanned, created, total, skipped, errors)
    on_error(archive_id, error_message)
    """
    if start_id < stop_id:
        return 0, 0

    scanned = 0
    created = 0
    skipped = 0
    errors = 0
    total = start_id - stop_id + 1
    if on_progress is not None:
        await on_progress(scanned, created, total, skipped, errors)

    # 按批次处理，每批先批量查库过滤已存在的
    current = start_id
    while current >= stop_id:
        batch_end = max(current - BATCH_CHECK_SIZE + 1, stop_id)
        batch_ids = [str(aid) for aid in range(current, batch_end - 1, -1)]
        batch_size = len(batch_ids)

        # 批量查询已存在的 ID（包含 miss 记录）
        existing_ids = await _batch_check_existing(db, batch_ids)
        missing_ids = [aid for aid in batch_ids if aid not in existing_ids]

        scanned += batch_size

        # 分小组并发拉取，避免一次并发过多
        chunk_size = 5
        batch_miss_ids: list[str] = []
        for i in range(0, len(missing_ids), chunk_size):
            chunk = missing_ids[i:i + chunk_size]
            results = await asyncio.gather(
                *[_fetch_and_upsert(db, aid, platform_id) for aid in chunk],
                return_exceptions=True,
            )
            for aid, r in zip(chunk, results):
                if isinstance(r, Exception):
                    errors += 1
                    err_msg = f"藏品 {aid} 请求异常: {r}"
                    logger.warning(err_msg)
                    if on_error is not None:
                        await on_error(aid, str(r))
                elif r is True:
                    created += 1
                elif r is False:
                    skipped += 1
                    batch_miss_ids.append(aid)

        # 批量记录本轮 miss
        await _record_misses(db, batch_miss_ids)

        if created % 20 == 0 and created > 0:
            await db.commit()

        if on_progress is not None:
            await on_progress(scanned, created, total, skipped, errors)

        current = batch_end - 1

    await db.commit()
    logger.info(f"藏品ID补齐完成: 扫描 {scanned}，新增 {created}，跳过 {skipped}，失败 {errors}")
    return scanned, created
