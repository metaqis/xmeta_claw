"""发行详情共享能力"""
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import LaunchDetail


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _normalize_source_id(source_id: str) -> Any:
    return int(source_id) if source_id.isdigit() else source_id


async def fetch_launch_detail_payload(source_id: str) -> Optional[dict]:
    resp = await crawler_client.post_safe(
        "/h5/news/launchCalendar/detailed",
        {"id": _normalize_source_id(source_id)},
    )
    if not resp:
        return None
    detail_data = resp.get("data")
    if not isinstance(detail_data, dict) or not detail_data:
        return None
    return detail_data


async def save_launch_detail(
    db: AsyncSession,
    launch_id: int,
    source_id: str,
    skip_existing: bool = True,
) -> bool:
    existing_result = await db.execute(
        select(LaunchDetail).where(LaunchDetail.launch_id == launch_id)
    )
    existing = existing_result.scalar_one_or_none()

    if skip_existing and existing:
        return False

    detail_data = await fetch_launch_detail_payload(source_id)
    if not detail_data:
        return False

    if existing:
        existing.priority_purchase_time = _parse_datetime(detail_data.get("priorityPurchaseTime"))
        existing.context_condition = detail_data.get("contextCondition")
        existing.status = str(detail_data.get("status")) if detail_data.get("status") is not None else None
        existing.raw_json = json.dumps(detail_data, ensure_ascii=False)
    else:
        detail = LaunchDetail(
            launch_id=launch_id,
            priority_purchase_time=_parse_datetime(detail_data.get("priorityPurchaseTime")),
            context_condition=detail_data.get("contextCondition"),
            status=str(detail_data.get("status")) if detail_data.get("status") is not None else None,
            raw_json=json.dumps(detail_data, ensure_ascii=False),
        )
        db.add(detail)
        await db.flush()
    return True
