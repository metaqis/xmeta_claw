"""平台与IP共享能力"""
from typing import Any, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import IP, Platform


async def get_or_create_platform(
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


async def get_or_create_ip(
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


async def ensure_platform_and_ip_from_calendar_item(
    db: AsyncSession,
    item: dict,
) -> Tuple[Optional[int], Optional[int]]:
    platform_id = None
    platform_api_id = item.get("platformId")
    platform_name = item.get("platformName")
    platform_icon = item.get("platformImg")
    if platform_api_id or platform_name:
        platform = await get_or_create_platform(db, platform_api_id, platform_name, platform_icon)
        platform_id = platform.id

    ip_id = None
    ip_name = item.get("ipName")
    ip_avatar = item.get("ipAvatar")
    if ip_name:
        ip_obj = await get_or_create_ip(db, ip_name, ip_avatar, platform_id)
        ip_id = ip_obj.id
    return platform_id, ip_id


async def find_platform_id_by_name(
    db: AsyncSession,
    name: Any,
) -> Optional[int]:
    if not name:
        return None
    result = await db.execute(select(Platform.id).where(Platform.name == str(name)))
    return result.scalar_one_or_none()


async def find_ip_id_by_name(
    db: AsyncSession,
    ip_name: Any,
) -> Optional[int]:
    if not ip_name:
        return None
    result = await db.execute(select(IP.id).where(IP.ip_name == str(ip_name)))
    return result.scalar_one_or_none()
