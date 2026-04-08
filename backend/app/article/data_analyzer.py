"""数据分析模块 — 为文章生成提供结构化数据"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, cast, Date, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    LaunchCalendar, LaunchDetail, Archive, IP, Platform,
    JingtanSkuWiki, JingtanSkuHomepageDetail,
)


async def _launch_rows(db: AsyncSession, start: datetime, end: datetime):
    result = await db.execute(
        select(
            LaunchCalendar,
            Platform.name.label("platform_name"),
            IP.ip_name,
        )
        .outerjoin(Platform, LaunchCalendar.platform_id == Platform.id)
        .outerjoin(IP, LaunchCalendar.ip_id == IP.id)
        .where(LaunchCalendar.sell_time >= start)
        .where(LaunchCalendar.sell_time < end)
        .order_by(LaunchCalendar.sell_time)
    )
    return result.all()


def _summarize_launches(rows) -> dict[str, Any]:
    launches: list[dict] = []
    total_supply = 0
    total_value = 0.0
    prices: list[float] = []
    platform_dist: dict[str, dict] = {}
    ip_dist: dict[str, dict] = {}

    for lc, platform_name, ip_name in rows:
        price = lc.price or 0
        count = lc.count or 0
        value = price * count
        pn = platform_name or "未知"
        ipn = ip_name or "未知"

        launches.append({
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

        platform_dist.setdefault(pn, {"count": 0, "value": 0.0})
        platform_dist[pn]["count"] += 1
        platform_dist[pn]["value"] += value

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
        "platform_distribution": sorted(
            [{"name": k, **v} for k, v in platform_dist.items()],
            key=lambda x: x["count"], reverse=True,
        ),
        "ip_distribution": sorted(
            [{"name": k, **v} for k, v in ip_dist.items()],
            key=lambda x: x["count"], reverse=True,
        ),
    }


async def _daily_trend(db: AsyncSession, start: datetime, end: datetime):
    result = await db.execute(
        select(
            cast(LaunchCalendar.sell_time, Date).label("d"),
            func.count(LaunchCalendar.id).label("cnt"),
            func.coalesce(func.sum(LaunchCalendar.price * LaunchCalendar.count), 0).label("val"),
        )
        .where(LaunchCalendar.sell_time >= start)
        .where(LaunchCalendar.sell_time < end)
        .group_by(cast(LaunchCalendar.sell_time, Date))
        .order_by(cast(LaunchCalendar.sell_time, Date))
    )
    return [{"date": str(r[0]), "count": r[1], "value": float(r[2])} for r in result.all()]


# ---------- 每日分析 ----------

async def get_daily_data(db: AsyncSession, target_date: str) -> dict[str, Any]:
    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    rows = await _launch_rows(db, date_obj, next_day)
    summary = _summarize_launches(rows)

    # 历史对比
    yesterday = date_obj - timedelta(days=1)
    yesterday_cnt = (await db.execute(
        select(func.count(LaunchCalendar.id))
        .where(and_(LaunchCalendar.sell_time >= yesterday, LaunchCalendar.sell_time < date_obj))
    )).scalar() or 0

    lw = date_obj - timedelta(days=7)
    lw_cnt = (await db.execute(
        select(func.count(LaunchCalendar.id))
        .where(and_(LaunchCalendar.sell_time >= lw, LaunchCalendar.sell_time < lw + timedelta(days=1)))
    )).scalar() or 0

    trend = await _daily_trend(db, date_obj - timedelta(days=6), next_day)

    # 当日发行 IP 的历史发行记录 (最近 30 天)
    ip_names = list({l["ip_name"] for l in summary["launches"] if l["ip_name"] != "未知"})
    ip_history: dict[str, int] = {}
    if ip_names:
        thirty_ago = date_obj - timedelta(days=30)
        for ipn in ip_names[:10]:
            cnt = (await db.execute(
                select(func.count(LaunchCalendar.id))
                .join(IP, LaunchCalendar.ip_id == IP.id)
                .where(and_(
                    IP.ip_name == ipn,
                    LaunchCalendar.sell_time >= thirty_ago,
                    LaunchCalendar.sell_time < date_obj,
                ))
            )).scalar() or 0
            ip_history[ipn] = cnt

    return {
        "date": target_date,
        **summary,
        "yesterday_launches": yesterday_cnt,
        "last_week_same_day_launches": lw_cnt,
        "daily_trend": trend,
        "ip_recent_30d_history": ip_history,
    }


# ---------- 每周分析 ----------

async def get_weekly_data(db: AsyncSession, end_date: str | None = None) -> dict[str, Any]:
    if end_date:
        end_obj = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end_obj = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # 本周: end_obj 所在周的周一到周日
    weekday = end_obj.weekday()
    week_start = end_obj - timedelta(days=weekday)
    week_end = week_start + timedelta(days=7)

    rows = await _launch_rows(db, week_start, week_end)
    summary = _summarize_launches(rows)
    trend = await _daily_trend(db, week_start, week_end)

    # 上周对比
    prev_start = week_start - timedelta(days=7)
    prev_end = week_start
    prev_rows = await _launch_rows(db, prev_start, prev_end)
    prev_summary = _summarize_launches(prev_rows)

    # 本周新增藏品
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

    # 热门 IP 排行
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


# ---------- 每月分析 ----------

async def get_monthly_data(db: AsyncSession, year: int, month: int) -> dict[str, Any]:
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)

    rows = await _launch_rows(db, month_start, month_end)
    summary = _summarize_launches(rows)
    trend = await _daily_trend(db, month_start, month_end)

    # 按周聚合
    weekly_data: list[dict] = []
    current = month_start
    week_num = 1
    while current < month_end:
        w_end = min(current + timedelta(days=7), month_end)
        w_rows = [r for r in rows if current <= (r[0].sell_time or month_start) < w_end]
        w_summary = _summarize_launches(w_rows)
        weekly_data.append({
            "week": week_num,
            "start": current.strftime("%m-%d"),
            "end": (w_end - timedelta(days=1)).strftime("%m-%d"),
            "launches": w_summary["total_launches"],
            "supply": w_summary["total_supply"],
            "value": w_summary["total_value"],
        })
        current = w_end
        week_num += 1

    # 上月对比
    if month == 1:
        prev_start = datetime(year - 1, 12, 1)
        prev_end = month_start
    else:
        prev_start = datetime(year, month - 1, 1)
        prev_end = month_start
    prev_rows = await _launch_rows(db, prev_start, prev_end)
    prev_summary = _summarize_launches(prev_rows)

    # 热门 IP
    ip_rank_result = await db.execute(
        select(IP.ip_name, func.count(LaunchCalendar.id).label("cnt"))
        .join(IP, LaunchCalendar.ip_id == IP.id)
        .where(LaunchCalendar.sell_time >= month_start)
        .where(LaunchCalendar.sell_time < month_end)
        .group_by(IP.ip_name)
        .order_by(func.count(LaunchCalendar.id).desc())
        .limit(10)
    )
    ip_ranking = [{"name": r[0], "count": r[1]} for r in ip_rank_result.all()]

    # 本月新增藏品数
    archive_count = (await db.execute(
        select(func.count(Archive.archive_id))
        .where(Archive.issue_time >= month_start)
        .where(Archive.issue_time < month_end)
    )).scalar() or 0

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
