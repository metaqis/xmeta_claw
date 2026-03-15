"""补齐 IP source_uid：通过关联藏品的详情接口获取 ipId"""
import asyncio
from typing import Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.crawler.ip_crawler import fetch_ip_profile, _extract_fans_count
from app.database.models import Archive, IP


async def _fetch_archive_detail_for_ip(archive_id: str, platform_id: Optional[int]) -> Optional[dict]:
    """获取藏品详情，仅用于提取 ipId"""
    payload = {
        "archiveId": archive_id,
        "platformId": str(platform_id) if platform_id is not None else "741",
        "active": "6",
        "page": 1,
        "pageSize": 20,
        "sellStatus": 1,
    }
    resp = await crawler_client.post_safe("/h5/goods/archive", payload)
    if not resp:
        return None
    data = resp.get("data")
    return data if isinstance(data, dict) else None


async def backfill_ip_source_uid(
    db: AsyncSession,
    on_progress: Callable[[int, int, int], Awaitable[None]] | None = None,
) -> Tuple[int, int]:
    """
    遍历 source_uid 为空的 IP，通过关联藏品的详情接口获取 ipId 并回填。

    Returns:
        (processed, updated) 元组
    """
    # 查询所有 source_uid 为空的 IP
    result = await db.execute(
        select(IP).where(IP.source_uid.is_(None)).order_by(IP.id)
    )
    ips_to_fix = result.scalars().all()

    total = len(ips_to_fix)
    if total == 0:
        logger.info("所有 IP 的 source_uid 均已填充，无需补齐")
        return 0, 0

    logger.info(f"发现 {total} 个 IP 缺少 source_uid，开始补齐...")
    if on_progress is not None:
        await on_progress(0, 0, total)

    processed = 0
    updated = 0

    for ip_obj in ips_to_fix:
        processed += 1

        # 找到一个关联的藏品
        archive_result = await db.execute(
            select(Archive.archive_id, Archive.platform_id)
            .where(Archive.ip_id == ip_obj.id)
            .limit(1)
        )
        archive_row = archive_result.first()

        if not archive_row:
            logger.debug(f"IP [{ip_obj.id}] {ip_obj.ip_name}: 无关联藏品，跳过")
            if on_progress is not None and (processed % 10 == 0 or processed == total):
                await on_progress(processed, updated, total)
            continue

        archive_id, platform_id = archive_row

        # 获取藏品详情获取 ipId
        detail = await _fetch_archive_detail_for_ip(archive_id, platform_id)
        if not detail:
            logger.debug(f"IP [{ip_obj.id}] {ip_obj.ip_name}: 藏品 {archive_id} 详情获取失败")
            if on_progress is not None and (processed % 10 == 0 or processed == total):
                await on_progress(processed, updated, total)
            continue

        source_uid = detail.get("ipId")
        try:
            source_uid_value = int(source_uid) if source_uid is not None else None
        except (ValueError, TypeError):
            source_uid_value = None

        if source_uid_value is None:
            logger.debug(f"IP [{ip_obj.id}] {ip_obj.ip_name}: 藏品 {archive_id} 详情中无 ipId")
            if on_progress is not None and (processed % 10 == 0 or processed == total):
                await on_progress(processed, updated, total)
            continue

        # 检查是否有其他 IP 已使用该 source_uid（避免唯一约束冲突）
        dup_result = await db.execute(
            select(IP.id).where(IP.source_uid == source_uid_value, IP.id != ip_obj.id)
        )
        if dup_result.scalar_one_or_none() is not None:
            logger.warning(
                f"IP [{ip_obj.id}] {ip_obj.ip_name}: source_uid={source_uid_value} 已被其他 IP 使用，跳过"
            )
            if on_progress is not None and (processed % 10 == 0 or processed == total):
                await on_progress(processed, updated, total)
            continue

        # 更新 source_uid
        ip_obj.source_uid = source_uid_value
        ip_obj.from_type = 1

        # 顺便补全 IP 详细信息
        profile = await fetch_ip_profile(source_uid_value, from_type=1)
        if profile:
            if profile.get("nickname"):
                ip_obj.ip_name = str(profile["nickname"])
            if profile.get("avatar") and not ip_obj.ip_avatar:
                ip_obj.ip_avatar = profile["avatar"]
            if profile.get("description") and not ip_obj.description:
                ip_obj.description = profile["description"]
            if ip_obj.fans_count is None:
                ip_obj.fans_count = _extract_fans_count(profile)

        updated += 1
        logger.info(
            f"[{processed}/{total}] IP [{ip_obj.id}] {ip_obj.ip_name} -> source_uid={source_uid_value}"
        )

        # 每 20 条提交一次
        if updated % 20 == 0:
            await db.commit()

        if on_progress is not None and (processed % 10 == 0 or processed == total):
            await on_progress(processed, updated, total)

    await db.commit()
    logger.info(f"IP source_uid 补齐完成: 处理 {processed}，更新 {updated}")
    return processed, updated
