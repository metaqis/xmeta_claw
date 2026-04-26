"""周报数据获取。"""
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Any

_BEIJING = timezone(timedelta(hours=8))

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    LaunchCalendar, IP,
    MarketDailySummary, MarketIPSnapshot,
    MarketPlaneSnapshot, MarketArchiveSnapshot, MarketTopCensus,
)
from app.article.queries import get_launch_rows, summarize_launches, get_daily_trend


async def _get_market_week_summary(
    db: AsyncSession, week_start: datetime, week_end: datetime
) -> dict:
    """汇总一周内每日全市场快照，返回聚合统计 + 每日趋势。"""
    start_date = week_start.date()
    end_date = (week_end - timedelta(days=1)).date()

    rows = (await db.execute(
        select(MarketDailySummary)
        .where(
            and_(
                MarketDailySummary.stat_date >= start_date,
                MarketDailySummary.stat_date <= end_date,
            )
        )
        .order_by(MarketDailySummary.stat_date)
    )).scalars().all()

    if not rows:
        return {"has_data": False}

    total_deal_count = sum(r.total_deal_count or 0 for r in rows)
    total_deal_amount = sum(r.total_deal_amount or 0 for r in rows)
    last_market_value = rows[-1].total_market_value if rows else None

    daily = [
        {
            "date": str(r.stat_date),
            "deal_count": r.total_deal_count,
            "deal_amount": r.total_deal_amount,
            "market_value": r.total_market_value,
            "top_ip": r.top_ip_name,
        }
        for r in rows
    ]

    return {
        "has_data": True,
        "total_deal_count": total_deal_count,
        "total_deal_amount": total_deal_amount,
        "last_market_value": last_market_value,
        "daily": daily,
    }


async def _get_ip_market_weekly(
    db: AsyncSession, week_start: datetime, week_end: datetime, limit: int = 10
) -> list[dict]:
    """聚合一周内 IP 市场快照，按累计成交量排名。"""
    start_date = week_start.date()
    end_date = (week_end - timedelta(days=1)).date()

    rows = (await db.execute(
        select(
            MarketIPSnapshot.name,
            func.sum(MarketIPSnapshot.deal_count).label("week_deal_count"),
            func.avg(MarketIPSnapshot.avg_amount).label("avg_price"),
            func.avg(MarketIPSnapshot.market_amount).label("avg_market_amount"),
        )
        .where(
            and_(
                MarketIPSnapshot.stat_date >= start_date,
                MarketIPSnapshot.stat_date <= end_date,
            )
        )
        .group_by(MarketIPSnapshot.name)
        .order_by(func.sum(MarketIPSnapshot.deal_count).desc())
        .limit(limit)
    )).all()

    return [
        {
            "name": r[0],
            "week_deal_count": int(r[1] or 0),
            "avg_price": round(float(r[2] or 0), 2),
            "avg_market_amount": round(float(r[3] or 0), 2),
        }
        for r in rows
    ]


async def _get_week_top_planes(
    db: AsyncSession, start_date: date_type, end_date: date_type, limit: int = 8
) -> list[dict]:
    """按板块聚合周内累计成交量，取 Top N。供 chart_plane_deal_rank 使用。"""
    rows = (await db.execute(
        select(
            MarketPlaneSnapshot.plane_name,
            func.sum(MarketPlaneSnapshot.deal_count).label("week_deal"),
        )
        .where(
            and_(
                MarketPlaneSnapshot.stat_date >= start_date,
                MarketPlaneSnapshot.stat_date <= end_date,
            )
        )
        .group_by(MarketPlaneSnapshot.plane_name)
        .order_by(func.sum(MarketPlaneSnapshot.deal_count).desc())
        .limit(limit)
    )).all()
    return [
        {
            "plane_name": r[0],
            "deal_count": int(r[1] or 0),
            "avg_price_rate": None,       # 周聚合无日涨跌幅，图表显示为灰色
            "total_market_value": None,
            "shelves_rate": None,
        }
        for r in rows
    ]


async def _get_week_hot_archives(
    db: AsyncSession, start_date: date_type, end_date: date_type, limit: int = 10
) -> list[dict]:
    """聚合周内成交量 Top N 藏品。供 chart_hot_archives_top10 使用。"""
    rows = (await db.execute(
        select(
            MarketArchiveSnapshot.archive_name,
            MarketArchiveSnapshot.top_name,
            func.sum(MarketArchiveSnapshot.deal_count).label("week_deal"),
            func.avg(MarketArchiveSnapshot.avg_amount).label("avg_price"),
            func.min(MarketArchiveSnapshot.min_amount).label("min_price"),
        )
        .where(
            and_(
                MarketArchiveSnapshot.stat_date >= start_date,
                MarketArchiveSnapshot.stat_date <= end_date,
            )
        )
        .group_by(MarketArchiveSnapshot.archive_name, MarketArchiveSnapshot.top_name)
        .order_by(func.sum(MarketArchiveSnapshot.deal_count).desc())
        .limit(limit)
    )).all()
    return [
        {
            "archive_name": r[0],
            "top_name": r[1],
            "deal_count": int(r[2] or 0),
            "avg_amount": round(float(r[3] or 0), 2),
            "avg_amount_rate": None,    # 周聚合无日涨跌幅
            "min_amount": round(float(r[4] or 0), 2) if r[4] else None,
            "market_amount": None,
        }
        for r in rows
    ]


async def _get_week_core_plane_values(
    db: AsyncSession, start_date: date_type, end_date: date_type
) -> list[dict]:
    """获取周内鲸探50/禁出195每日市值序列，供 chart_core_plane_market_line 使用。"""
    rows = (await db.execute(
        select(MarketTopCensus)
        .where(
            and_(
                MarketTopCensus.stat_date >= start_date,
                MarketTopCensus.stat_date <= end_date,
                MarketTopCensus.top_name.in_(["鲸探50", "禁出195"]),
            )
        )
        .order_by(MarketTopCensus.stat_date, MarketTopCensus.top_name)
    )).scalars().all()

    # 构建按日期的映射
    value_map: dict[date_type, dict] = {}
    cur = start_date
    while cur <= end_date:
        value_map[cur] = {"jingtan50": None, "restricted_relics": None}
        cur += timedelta(days=1)

    for r in rows:
        if r.top_name == "鲸探50":
            value_map[r.stat_date]["jingtan50"] = float(r.total_market_amount or 0)
        elif r.top_name == "禁出195":
            value_map[r.stat_date]["restricted_relics"] = float(r.total_market_amount or 0)

    return [
        {
            "stat_date": str(d),
            "jingtan50_market_value": value_map[d]["jingtan50"],
            "restricted_relics_market_value": value_map[d]["restricted_relics"],
        }
        for d in sorted(value_map)
        if value_map[d]["jingtan50"] is not None or value_map[d]["restricted_relics"] is not None
    ]


async def get_weekly_data(db: AsyncSession, end_date: str | None = None) -> dict[str, Any]:
    if end_date:
        end_obj = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_obj = datetime.now(_BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)

    weekday    = end_obj.weekday()
    week_start = end_obj - timedelta(days=weekday)   # 本周周一 00:00
    week_end   = week_start + timedelta(days=7)       # 下周周一 00:00（不含）

    week_start_date = week_start.date()
    week_end_date   = (week_end - timedelta(days=1)).date()   # 本周周日

    prev_start = week_start - timedelta(days=7)
    prev_end   = week_start
    prev_start_date = prev_start.date()
    prev_end_date   = (prev_end - timedelta(days=1)).date()

    prev2_start = prev_start - timedelta(days=7)
    prev2_end   = prev_start

    # ── 本周发行数据 ──────────────────────────────────────────────────────────
    rows    = await get_launch_rows(db, week_start, week_end)
    summary = summarize_launches(rows)
    trend   = await get_daily_trend(db, week_start, week_end)

    # ── 上周、上上周发行数据 ──────────────────────────────────────────────────
    prev_rows     = await get_launch_rows(db, prev_start, prev_end)
    prev_summary  = summarize_launches(prev_rows)
    prev2_rows    = await get_launch_rows(db, prev2_start, prev2_end)
    prev2_summary = summarize_launches(prev2_rows)

    # ── IP 发行排行（本周 + 上周） ────────────────────────────────────────────
    async def _ip_rank(start, end):
        r = await db.execute(
            select(IP.ip_name, func.count(LaunchCalendar.id).label("cnt"))
            .join(IP, LaunchCalendar.ip_id == IP.id)
            .where(LaunchCalendar.sell_time >= start)
            .where(LaunchCalendar.sell_time < end)
            .where(LaunchCalendar.platform_id == 741)
            .group_by(IP.ip_name)
            .order_by(func.count(LaunchCalendar.id).desc())
            .limit(10)
        )
        return [{"name": row[0], "count": row[1]} for row in r.all()]

    ip_ranking      = await _ip_rank(week_start, week_end)
    prev_ip_ranking = await _ip_rank(prev_start, prev_end)

    # ── 市场行情（三周） ──────────────────────────────────────────────────────
    market_week       = await _get_market_week_summary(db, week_start, week_end)
    market_prev_week  = await _get_market_week_summary(db, prev_start, prev_end)
    market_prev2_week = await _get_market_week_summary(db, prev2_start, prev2_end)

    # ── IP 市场成交排行（本周 + 上周） ────────────────────────────────────────
    ip_market_weekly      = await _get_ip_market_weekly(db, week_start, week_end)
    prev_ip_market_weekly = await _get_ip_market_weekly(db, prev_start, prev_end)

    # ── 本周板块累计成交 Top8 ─────────────────────────────────────────────────
    week_top_planes = await _get_week_top_planes(db, week_start_date, week_end_date)

    # ── 本周热门藏品累计成交 Top10 ────────────────────────────────────────────
    week_hot_archives = await _get_week_hot_archives(db, week_start_date, week_end_date)

    # ── 核心板块（鲸探50/禁出195）本周每日市值 ───────────────────────────────
    week_core_plane_values = await _get_week_core_plane_values(
        db, week_start_date, week_end_date
    )

    # ── Python 预计算环比（LLM 直接引用，不得自行推算） ──────────────────────
    def _pct(cur, prev):
        if prev and prev > 0:
            return round((cur - prev) / prev * 100, 1)
        return None

    launches_pct     = _pct(summary["total_launches"], prev_summary["total_launches"])
    value_pct        = _pct(summary["total_value"], prev_summary["total_value"])
    supply_pct       = _pct(summary["total_supply"], prev_summary["total_supply"])
    avg_price_pct    = _pct(summary["avg_price"], prev_summary["avg_price"])

    market_deal_pct   = None
    market_amount_pct = None
    if market_week.get("has_data") and market_prev_week.get("has_data"):
        market_deal_pct   = _pct(market_week["total_deal_count"], market_prev_week["total_deal_count"])
        market_amount_pct = _pct(market_week["total_deal_amount"], market_prev_week["total_deal_amount"])

    return {
        "start_date": week_start.strftime("%Y-%m-%d"),
        "end_date": (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        # 本周发行（summarize_launches 展开：launches, total_launches, total_supply, total_value,
        #           avg_price, max_price, min_price, ip_distribution）
        **summary,
        "daily_trend": trend,
        "ip_ranking": ip_ranking,
        # 上周/上上周发行（三周对比用）
        "prev_week": {
            "start_date": prev_start.strftime("%Y-%m-%d"),
            "end_date": (prev_end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "total_launches": prev_summary["total_launches"],
            "total_supply": prev_summary["total_supply"],
            "total_value": prev_summary["total_value"],
            "avg_price": prev_summary["avg_price"],
            "ip_ranking": prev_ip_ranking,
        },
        "prev2_week": {
            "start_date": prev2_start.strftime("%Y-%m-%d"),
            "end_date": (prev2_end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "total_launches": prev2_summary["total_launches"],
            "total_supply": prev2_summary["total_supply"],
            "total_value": prev2_summary["total_value"],
            "avg_price": prev2_summary["avg_price"],
        },
        # 预计算发行环比
        "launches_pct": launches_pct,
        "value_pct": value_pct,
        "supply_pct": supply_pct,
        "avg_price_pct": avg_price_pct,
        # 市场行情
        "market_week": market_week,
        "market_prev_week": market_prev_week,
        "market_prev2_week": market_prev2_week,
        "market_deal_pct": market_deal_pct,
        "market_amount_pct": market_amount_pct,
        "ip_market_weekly": ip_market_weekly,
        "prev_ip_market_weekly": prev_ip_market_weekly,
        # 本周市场深度数据
        "week_top_planes": week_top_planes,
        "week_hot_archives": week_hot_archives,
        "week_core_plane_values": week_core_plane_values,
        # 兼容旧字段
        "prev_week_launches": prev_summary["total_launches"],
        "prev_week_value": prev_summary["total_value"],
        "launches_change": summary["total_launches"] - prev_summary["total_launches"],
        "value_change": summary["total_value"] - prev_summary["total_value"],
    }



