"""周报数据获取。"""
from datetime import datetime, timezone, timedelta
from typing import Any

_BEIJING = timezone(timedelta(hours=8))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LaunchCalendar, Archive, IP, Platform
from app.article.queries import get_launch_rows, summarize_launches, get_daily_trend


async def get_weekly_data(db: AsyncSession, end_date: str | None = None) -> dict[str, Any]:
    if end_date:
        end_obj = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_obj = datetime.now(_BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)

    weekday   = end_obj.weekday()
    week_start = end_obj - timedelta(days=weekday)
    week_end   = week_start + timedelta(days=7)

    rows    = await get_launch_rows(db, week_start, week_end)
    summary = summarize_launches(rows)
    trend   = await get_daily_trend(db, week_start, week_end)

    prev_start = week_start - timedelta(days=7)
    prev_rows  = await get_launch_rows(db, prev_start, week_start)
    prev_summary = summarize_launches(prev_rows)

    new_archives_result = await db.execute(
        select(
            Archive.archive_id, Archive.archive_name, Archive.img,
            Archive.total_goods_count, Archive.archive_type,
            Platform.name.label("platform_name"), IP.ip_name,
        )
        .outerjoin(Platform, Archive.platform_id == Platform.id)
        .outerjoin(IP, Archive.ip_id == IP.id)
        .where(Archive.issue_time >= week_start)
        .where(Archive.issue_time < week_end)
        .order_by(Archive.issue_time.desc())
        .limit(20)
    )
    new_archives = [
        {
            "archive_id": r[0], "name": r[1], "img": r[2],
            "goods_count": r[3], "type": r[4],
            "platform": r[5] or "未知", "ip": r[6] or "未知",
        }
        for r in new_archives_result.all()
    ]

    ip_rank_result = await db.execute(
        select(IP.ip_name, func.count(LaunchCalendar.id).label("cnt"))
        .join(IP, LaunchCalendar.ip_id == IP.id)
        .where(LaunchCalendar.sell_time >= week_start)
        .where(LaunchCalendar.sell_time < week_end)
        .group_by(IP.ip_name)
        .order_by(func.count(LaunchCalendar.id).desc())
        .limit(10)
    )
    ip_ranking = [{"name": r[0], "count": r[1]} for r in ip_rank_result.all()]

    return {
        "start_date": week_start.strftime("%Y-%m-%d"),
        "end_date": (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        **summary,
        "daily_trend": trend,
        "prev_week_launches": prev_summary["total_launches"],
        "prev_week_value": prev_summary["total_value"],
        "launches_change": summary["total_launches"] - prev_summary["total_launches"],
        "value_change": summary["total_value"] - prev_summary["total_value"],
        "new_archives": new_archives,
        "ip_ranking": ip_ranking,
    }

