"""月报数据获取。"""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LaunchCalendar, Archive, IP
from app.article.queries import get_launch_rows, summarize_launches, get_daily_trend


async def get_monthly_data(db: AsyncSession, year: int, month: int) -> dict[str, Any]:
    month_start = datetime(year, month, 1)
    month_end   = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    rows    = await get_launch_rows(db, month_start, month_end)
    summary = summarize_launches(rows)
    trend   = await get_daily_trend(db, month_start, month_end)

    # 按周聚合
    weekly_data: list[dict] = []
    current  = month_start
    week_num = 1
    while current < month_end:
        w_end  = min(current + timedelta(days=7), month_end)
        w_rows = [r for r in rows if current <= (r[0].sell_time or month_start) < w_end]
        w_summary = summarize_launches(w_rows)
        weekly_data.append({
            "week": week_num,
            "start": current.strftime("%m-%d"),
            "end": (w_end - timedelta(days=1)).strftime("%m-%d"),
            "launches": w_summary["total_launches"],
            "supply": w_summary["total_supply"],
            "value": w_summary["total_value"],
        })
        current  = w_end
        week_num += 1

    if month == 1:
        prev_start = datetime(year - 1, 12, 1)
    else:
        prev_start = datetime(year, month - 1, 1)
    prev_rows    = await get_launch_rows(db, prev_start, month_start)
    prev_summary = summarize_launches(prev_rows)

    ip_rank_result = await db.execute(
        select(IP.ip_name, func.count(LaunchCalendar.id).label("cnt"))
        .join(IP, LaunchCalendar.ip_id == IP.id)
        .where(LaunchCalendar.sell_time >= month_start)
        .where(LaunchCalendar.sell_time < month_end)
        .where(LaunchCalendar.platform_id == 741)
        .group_by(IP.ip_name)
        .order_by(func.count(LaunchCalendar.id).desc())
        .limit(10)
    )
    ip_ranking = [{"name": r[0], "count": r[1]} for r in ip_rank_result.all()]

    archive_count = (
        await db.execute(
            select(func.count(Archive.archive_id))
            .where(Archive.issue_time >= month_start)
            .where(Archive.issue_time < month_end)
            .where(Archive.platform_id == 741)
        )
    ).scalar() or 0

    return {
        "year": year,
        "month": month,
        "month_label": f"{year}年{month}月",
        **summary,
        "daily_trend": trend,
        "weekly_breakdown": weekly_data,
        "prev_month_launches": prev_summary["total_launches"],
        "prev_month_value": prev_summary["total_value"],
        "launches_change": summary["total_launches"] - prev_summary["total_launches"],
        "value_change": summary["total_value"] - prev_summary["total_value"],
        "ip_ranking": ip_ranking,
        "new_archive_count": archive_count,
    }
