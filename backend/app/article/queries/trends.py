"""时间序列查询 — 发行趋势聚合。"""
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LaunchCalendar


async def get_daily_trend(db: AsyncSession, start, end) -> list[dict]:
    """按日聚合发行数量和总价值，返回列表。"""
    result = await db.execute(
        select(
            cast(LaunchCalendar.sell_time, Date).label("d"),
            func.count(LaunchCalendar.id).label("cnt"),
            func.coalesce(
                func.sum(LaunchCalendar.price * LaunchCalendar.count), 0
            ).label("val"),
        )
        .where(LaunchCalendar.sell_time >= start)
        .where(LaunchCalendar.sell_time < end)
        .group_by(cast(LaunchCalendar.sell_time, Date))
        .order_by(cast(LaunchCalendar.sell_time, Date))
    )
    return [{"date": str(r[0]), "count": r[1], "value": float(r[2])} for r in result.all()]
