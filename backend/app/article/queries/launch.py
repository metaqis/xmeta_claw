"""发行日历基础查询 — 行数据获取与汇总。"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LaunchCalendar, Platform, IP


async def get_launch_rows(db: AsyncSession, start, end):
    """查询 [start, end) 时间段内所有发行项（含平台名、IP名）。"""
    result = await db.execute(
        select(LaunchCalendar, Platform.name.label("platform_name"), IP.ip_name)
        .outerjoin(Platform, LaunchCalendar.platform_id == Platform.id)
        .outerjoin(IP, LaunchCalendar.ip_id == IP.id)
        .where(LaunchCalendar.sell_time >= start)
        .where(LaunchCalendar.sell_time < end)
        .order_by(LaunchCalendar.sell_time)
    )
    return result.all()


def summarize_launches(rows) -> dict[str, Any]:
    """将查询结果汇总为统计字典 + 发行项列表。"""
    launches: list[dict] = []
    total_supply = 0
    total_value = 0.0
    prices: list[float] = []
    ip_dist: dict[str, dict] = {}

    for lc, platform_name, ip_name in rows:
        price = lc.price or 0
        count = lc.count or 0
        value = price * count
        pn = platform_name or "未知"
        ipn = ip_name or "未知"

        launches.append({
            "launch_id": lc.id,
            "source_id": lc.source_id or "",
            "name": lc.name,
            "sell_time": lc.sell_time.strftime("%Y-%m-%d %H:%M") if lc.sell_time else "",
            "price": price,
            "count": count,
            "value": value,
            "platform_name": pn,
            "ip_name": ipn,
            "img": lc.img or "",
            "is_priority_purchase": bool(lc.is_priority_purchase),
            "priority_purchase_num": lc.priority_purchase_num or 0,
        })
        total_supply += count
        total_value += value
        if price > 0:
            prices.append(price)

        ip_dist.setdefault(ipn, {"count": 0, "value": 0.0})
        ip_dist[ipn]["count"] += 1
        ip_dist[ipn]["value"] += value

    return {
        "launches": launches,
        "total_launches": len(launches),
        "total_supply": total_supply,
        "total_value": total_value,
        "avg_price": round(sum(prices) / len(prices), 2) if prices else 0,
        "max_price": max(prices) if prices else 0,
        "min_price": min(prices) if prices else 0,
        "ip_distribution": sorted(
            [{"name": k, **v} for k, v in ip_dist.items()],
            key=lambda x: x["count"],
            reverse=True,
        ),
    }
