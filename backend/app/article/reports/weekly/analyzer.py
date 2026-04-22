"""周报数据获取。"""
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Any

_BEIJING = timezone(timedelta(hours=8))

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    LaunchCalendar, Archive, IP, Platform,
    MarketDailySummary, MarketIPSnapshot,
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
    # 市值取最后一天（存量指标，不宜累加）
    last_market_value = rows[-1].total_market_value if rows else None

    # 日成交趋势
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


async def get_weekly_data(db: AsyncSession, end_date: str | None = None) -> dict[str, Any]:
    if end_date:
        end_obj = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_obj = datetime.now(_BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)

    weekday    = end_obj.weekday()
    week_start = end_obj - timedelta(days=weekday)
    week_end   = week_start + timedelta(days=7)

    # ── 本周发行数据 ──────────────────────────────────────────────────────────
    rows    = await get_launch_rows(db, week_start, week_end)
    summary = summarize_launches(rows)
    trend   = await get_daily_trend(db, week_start, week_end)

    # ── 上周发行数据 ──────────────────────────────────────────────────────────
    prev_start   = week_start - timedelta(days=7)
    prev_rows    = await get_launch_rows(db, prev_start, week_start)
    prev_summary = summarize_launches(prev_rows)

    # ── 上上周发行数据（三周比较） ────────────────────────────────────────────
    prev2_start   = prev_start - timedelta(days=7)
    prev2_rows    = await get_launch_rows(db, prev2_start, prev_start)
    prev2_summary = summarize_launches(prev2_rows)

    # ── 本周 IP 发行排行 ───────────────────────────────────────────────────────
    ip_rank_result = await db.execute(
        select(IP.ip_name, func.count(LaunchCalendar.id).label("cnt"))
        .join(IP, LaunchCalendar.ip_id == IP.id)
        .where(LaunchCalendar.sell_time >= week_start)
        .where(LaunchCalendar.sell_time < week_end)
        .where(LaunchCalendar.platform_id == 741)
        .group_by(IP.ip_name)
        .order_by(func.count(LaunchCalendar.id).desc())
        .limit(10)
    )
    ip_ranking = [{"name": r[0], "count": r[1]} for r in ip_rank_result.all()]

    # ── 上周 IP 发行排行（用于对比） ──────────────────────────────────────────
    prev_ip_rank = await db.execute(
        select(IP.ip_name, func.count(LaunchCalendar.id).label("cnt"))
        .join(IP, LaunchCalendar.ip_id == IP.id)
        .where(LaunchCalendar.sell_time >= prev_start)
        .where(LaunchCalendar.sell_time < week_start)
        .where(LaunchCalendar.platform_id == 741)
        .group_by(IP.ip_name)
        .order_by(func.count(LaunchCalendar.id).desc())
        .limit(10)
    )
    prev_ip_ranking = [{"name": r[0], "count": r[1]} for r in prev_ip_rank.all()]

    # ── 本周新增藏品 ───────────────────────────────────────────────────────────
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
        .where(Archive.platform_id == 741)
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

    # ── 本周市场行情汇总（MarketDailySummary） ────────────────────────────────
    market_week      = await _get_market_week_summary(db, week_start, week_end)
    market_prev_week = await _get_market_week_summary(db, prev_start, week_start)
    market_prev2_week = await _get_market_week_summary(db, prev2_start, prev_start)

    # ── 本周 IP 市场排行（MarketIPSnapshot 累计成交量） ────────────────────────
    ip_market_weekly = await _get_ip_market_weekly(db, week_start, week_end)
    prev_ip_market_weekly = await _get_ip_market_weekly(db, prev_start, week_start)

    # ── 环比计算（Python预计算，LLM直接使用） ────────────────────────────────
    def _pct(cur, prev):
        if prev and prev > 0:
            return round((cur - prev) / prev * 100, 1)
        return None

    launches_pct    = _pct(summary["total_launches"], prev_summary["total_launches"])
    value_pct       = _pct(summary["total_value"], prev_summary["total_value"])
    supply_pct      = _pct(summary["total_supply"], prev_summary["total_supply"])

    market_deal_pct = None
    if market_week.get("has_data") and market_prev_week.get("has_data"):
        market_deal_pct = _pct(
            market_week["total_deal_count"],
            market_prev_week["total_deal_count"],
        )

    return {
        "start_date": week_start.strftime("%Y-%m-%d"),
        "end_date": (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        # 本周发行
        **summary,
        "daily_trend": trend,
        "ip_ranking": ip_ranking,
        "new_archives": new_archives,
        # 上周发行（含上上周用于三周比较）
        "prev_week": {
            "start_date": prev_start.strftime("%Y-%m-%d"),
            "end_date": (week_start - timedelta(days=1)).strftime("%Y-%m-%d"),
            "total_launches": prev_summary["total_launches"],
            "total_supply": prev_summary["total_supply"],
            "total_value": prev_summary["total_value"],
            "avg_price": prev_summary["avg_price"],
            "ip_ranking": prev_ip_ranking,
        },
        "prev2_week": {
            "start_date": prev2_start.strftime("%Y-%m-%d"),
            "end_date": (prev_start - timedelta(days=1)).strftime("%Y-%m-%d"),
            "total_launches": prev2_summary["total_launches"],
            "total_supply": prev2_summary["total_supply"],
            "total_value": prev2_summary["total_value"],
            "avg_price": prev2_summary["avg_price"],
        },
        # Python 预计算环比
        "launches_pct": launches_pct,
        "value_pct": value_pct,
        "supply_pct": supply_pct,
        # 本周市场行情
        "market_week": market_week,
        "market_prev_week": market_prev_week,
        "market_prev2_week": market_prev2_week,
        "market_deal_pct": market_deal_pct,
        "ip_market_weekly": ip_market_weekly,
        "prev_ip_market_weekly": prev_ip_market_weekly,
        # 兼容旧字段（prompt 里有引用）
        "prev_week_launches": prev_summary["total_launches"],
        "prev_week_value": prev_summary["total_value"],
        "launches_change": summary["total_launches"] - prev_summary["total_launches"],
        "value_change": summary["total_value"] - prev_summary["total_value"],
    }
