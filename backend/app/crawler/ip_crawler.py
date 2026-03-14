from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import IP


def _extract_fans_count(profile: dict) -> Optional[int]:
    for key in ("fansCount", "fansNum", "fans", "followerCount", "followCount"):
        if key in profile and profile.get(key) is not None:
            try:
                return int(profile.get(key))
            except (ValueError, TypeError):
                return None
    return None


async def fetch_ip_profile(source_uid: int, from_type: int = 1) -> Optional[dict]:
    resp = await crawler_client.post_safe(
        "/h5/community/userHome",
        {"uid": str(source_uid), "fromType": str(from_type)},
    )
    if not resp:
        return None
    data = resp.get("data")
    return data if isinstance(data, dict) else None


async def get_or_create_ip_by_source_uid(
    db: AsyncSession,
    source_uid: int,
    platform_id: Optional[int],
    from_type: int = 1,
    fallback_name: Optional[str] = None,
    fallback_avatar: Optional[str] = None,
) -> Optional[IP]:
    result = await db.execute(select(IP).where(IP.source_uid == source_uid))
    ip_obj = result.scalar_one_or_none()
    if ip_obj:
        if platform_id is not None and ip_obj.platform_id is None:
            ip_obj.platform_id = platform_id
        if (not ip_obj.description) or (not ip_obj.ip_avatar) or (not ip_obj.ip_name) or (ip_obj.fans_count is None):
            profile = await fetch_ip_profile(source_uid, from_type=from_type)
            if profile:
                if profile.get("nickname"):
                    ip_obj.ip_name = str(profile["nickname"])
                if profile.get("avatar") and not ip_obj.ip_avatar:
                    ip_obj.ip_avatar = profile["avatar"]
                if profile.get("description") and not ip_obj.description:
                    ip_obj.description = profile["description"]
                if ip_obj.fans_count is None:
                    ip_obj.fans_count = _extract_fans_count(profile)
        return ip_obj

    if fallback_name:
        result = await db.execute(
            select(IP).where(IP.ip_name == fallback_name, IP.platform_id == platform_id)
        )
        ip_obj = result.scalar_one_or_none()
        if ip_obj and ip_obj.source_uid is None:
            ip_obj.source_uid = source_uid
            ip_obj.from_type = from_type
            profile = await fetch_ip_profile(source_uid, from_type=from_type)
            if profile:
                if profile.get("nickname"):
                    ip_obj.ip_name = str(profile["nickname"])
                if profile.get("avatar"):
                    ip_obj.ip_avatar = profile["avatar"]
                if profile.get("description"):
                    ip_obj.description = profile["description"]
                ip_obj.fans_count = _extract_fans_count(profile)
            else:
                if fallback_avatar and not ip_obj.ip_avatar:
                    ip_obj.ip_avatar = fallback_avatar
            return ip_obj

    profile = await fetch_ip_profile(source_uid, from_type=from_type)
    if profile:
        nickname = profile.get("nickname") or fallback_name or f"uid:{source_uid}"
        avatar = profile.get("avatar") or fallback_avatar
        description = profile.get("description")
        fans_count = _extract_fans_count(profile)
    else:
        nickname = fallback_name or f"uid:{source_uid}"
        avatar = fallback_avatar
        description = None
        fans_count = None

    ip_obj = IP(
        source_uid=source_uid,
        from_type=from_type,
        ip_name=str(nickname),
        ip_avatar=avatar,
        description=description,
        fans_count=fans_count,
        platform_id=platform_id,
    )
    db.add(ip_obj)
    await db.flush()
    return ip_obj
