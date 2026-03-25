from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import Plane


def _to_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def import_planes_to_db(db: AsyncSession) -> int:
    payload = await crawler_client.post_safe(
        "/h5/plane/listNew",
        {"type": 0, "pageNum": 1, "pageSize": 100},
    )
    if not isinstance(payload, dict):
        raise RuntimeError("板块接口请求失败")

    records = payload.get("data")
    if not isinstance(records, list):
        raise ValueError("JSON 格式错误: data 必须为数组")

    saved = 0
    for item in records:
        code = str(item.get("code") or "").strip()
        if not code:
            continue

        result = await db.execute(select(Plane).where(Plane.code == code))
        existing = result.scalar_one_or_none()
        source_id = _to_int(item.get("id"))
        if existing:
            existing.source_id = source_id
            existing.name = str(item.get("name") or existing.name)
            existing.img = item.get("img")
            existing.description = item.get("description")
        else:
            db.add(
                Plane(
                    source_id=source_id,
                    code=code,
                    name=str(item.get("name") or ""),
                    img=item.get("img"),
                    description=item.get("description"),
                )
            )
        saved += 1

    await db.commit()
    return saved
