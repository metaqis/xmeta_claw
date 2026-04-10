"""日报数据获取 — 汇总当日发行数据、增强含品信息、IP深度画像。"""
from datetime import datetime, timedelta, date as date_type
from typing import Any

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    LaunchCalendar, IP,
    MarketDailySummary, MarketPlaneSnapshot, MarketPlaneCensus,
    MarketTopCensus, MarketArchiveSnapshot,
)
from app.article.queries import (
    get_launch_rows,
    summarize_launches,
    get_daily_trend,
    enrich_daily_launches,
    get_ip_deep_analysis,
    get_owner_sku_counts,
    get_owner_portfolios,
)


async def get_daily_data(db: AsyncSession, target_date: str) -> dict[str, Any]:
    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    rows = await get_launch_rows(db, date_obj, next_day)
    summary = summarize_launches(rows)

    # 历史对比
    yesterday = date_obj - timedelta(days=1)
    yesterday_cnt = (
        await db.execute(
            select(func.count(LaunchCalendar.id)).where(
                and_(LaunchCalendar.sell_time >= yesterday, LaunchCalendar.sell_time < date_obj)
            )
        )
    ).scalar() or 0

    lw = date_obj - timedelta(days=7)
    lw_cnt = (
        await db.execute(
            select(func.count(LaunchCalendar.id)).where(
                and_(
                    LaunchCalendar.sell_time >= lw,
                    LaunchCalendar.sell_time < lw + timedelta(days=1),
                )
            )
        )
    ).scalar() or 0

    trend = await get_daily_trend(db, date_obj - timedelta(days=6), next_day)

    # 近30天各IP发行次数
    ip_names = list({l["ip_name"] for l in summary["launches"] if l["ip_name"] != "未知"})
    ip_history: dict[str, int] = {}
    if ip_names:
        thirty_ago = date_obj - timedelta(days=30)
        for ipn in ip_names[:10]:
            cnt = (
                await db.execute(
                    select(func.count(LaunchCalendar.id))
                    .join(IP, LaunchCalendar.ip_id == IP.id)
                    .where(
                        and_(
                            IP.ip_name == ipn,
                            LaunchCalendar.sell_time >= thirty_ago,
                            LaunchCalendar.sell_time < date_obj,
                        )
                    )
                )
            ).scalar() or 0
            ip_history[ipn] = cnt

    # 含品增强
    enriched_launches = await enrich_daily_launches(db, summary["launches"])

    # IP 深度画像
    ip_deep = await get_ip_deep_analysis(db, ip_names, date_obj)

    # 聚合今日发行主体
    all_owners_today: list[str] = []
    ip_owners_map: dict[str, list[str]] = {}
    for el in enriched_launches:
        ipn = el.get("ip_name") or "未知"
        for ca in el.get("contain_archives") or []:
            owner = ca.get("owner") or ""
            if owner:
                if owner not in all_owners_today:
                    all_owners_today.append(owner)
                ip_owners_map.setdefault(ipn, [])
                if owner not in ip_owners_map[ipn]:
                    ip_owners_map[ipn].append(owner)

    owner_total_counts = await get_owner_sku_counts(db, all_owners_today)
    owner_recent = await get_owner_portfolios(db, all_owners_today, limit=4)

    for ipn, owners in ip_owners_map.items():
        if ipn not in ip_deep:
            ip_deep[ipn] = {
                "total_launches": 0, "recent_30d_launches": 0,
                "fans_count": 0, "description": "", "recent_archives": [],
            }
        ip_deep[ipn]["owners"] = [
            {
                "name": o,
                "total_sku_count": owner_total_counts.get(o, 0),
                "recent_works": [w["name"] for w in owner_recent.get(o, [])[:4]],
            }
            for o in owners
        ]

    return {
        "date": target_date,
        **summary,
        "enriched_launches": enriched_launches,
        "yesterday_launches": yesterday_cnt,
        "last_week_same_day_launches": lw_cnt,
        "daily_trend": trend,
        "ip_recent_30d_history": ip_history,
        "ip_deep_analysis": ip_deep,
        "market_analysis": await get_market_snapshot_data(db, date_obj),
    }


async def get_market_snapshot_data(db: AsyncSession, target_date: datetime) -> dict[str, Any]:
    """查询昨日（target_date-1）和前日（target_date-2）的行情数据，返回结构化摘要。"""
    yesterday: date_type = (target_date - timedelta(days=1)).date()
    day_before: date_type = (target_date - timedelta(days=2)).date()

    async def _fetch_summary(d: date_type) -> dict | None:
        row = (await db.execute(
            select(MarketDailySummary).where(MarketDailySummary.stat_date == d)
        )).scalar_one_or_none()
        if row is None:
            return None
        return {
            "stat_date": str(d),
            "total_deal_count": row.total_deal_count,
            "total_deal_amount": row.total_deal_amount,
            "total_market_value": row.total_market_value,
            "active_plane_count": row.active_plane_count,
            "top_plane_name": row.top_plane_name,
            "top_plane_deal_count": row.top_plane_deal_count,
            "top_ip_name": row.top_ip_name,
            "top_ip_deal_count": row.top_ip_deal_count,
        }

    async def _fetch_top_planes(d: date_type, limit: int = 8) -> list[dict]:
        rows = (await db.execute(
            select(MarketPlaneSnapshot)
            .where(MarketPlaneSnapshot.stat_date == d)
            .order_by(desc(MarketPlaneSnapshot.deal_count))
            .limit(limit)
        )).scalars().all()
        return [
            {
                "plane_name": r.plane_name,
                "deal_count": r.deal_count,
                "deal_price": r.deal_price,
                "avg_price": r.avg_price,        # 涨跌幅 %
                "total_market_value": r.total_market_value,
                "shelves_rate": r.shelves_rate,
            }
            for r in rows
        ]

    async def _fetch_plane_census(d: date_type) -> list[dict]:
        rows = (await db.execute(
            select(MarketPlaneCensus)
            .where(MarketPlaneCensus.stat_date == d)
            .order_by(desc(MarketPlaneCensus.total_deal_count))
            .limit(10)
        )).scalars().all()
        return [
            {
                "plane_name": r.plane_name,
                "total_deal_count": r.total_deal_count,
                "total_deal_count_rate": r.total_deal_count_rate,
                "total_market_amount": r.total_market_amount,
                "total_market_amount_rate": r.total_market_amount_rate,
                "up_archive_count": r.up_archive_count,
                "down_archive_count": r.down_archive_count,
                "total_archive_count": r.total_archive_count,
            }
            for r in rows
        ]

    async def _fetch_top_census(d: date_type) -> list[dict]:
        rows = (await db.execute(
            select(MarketTopCensus)
            .where(MarketTopCensus.stat_date == d)
            .order_by(desc(MarketTopCensus.total_deal_count))
        )).scalars().all()
        return [
            {
                "top_name": r.top_name,
                "total_deal_count": r.total_deal_count,
                "total_deal_count_rate": r.total_deal_count_rate,
                "total_market_amount": r.total_market_amount,
                "total_market_amount_rate": r.total_market_amount_rate,
                "up_archive_count": r.up_archive_count,
                "down_archive_count": r.down_archive_count,
                "total_archive_count": r.total_archive_count,
            }
            for r in rows
        ]

    async def _fetch_top_archives(d: date_type, limit_per_cat: int = 5) -> list[dict]:
        """取各行情分类 Top N 藏品（按成交量）。"""
        rows = (await db.execute(
            select(MarketArchiveSnapshot)
            .where(
                and_(
                    MarketArchiveSnapshot.stat_date == d,
                    MarketArchiveSnapshot.rank <= limit_per_cat,
                )
            )
            .order_by(MarketArchiveSnapshot.top_name, MarketArchiveSnapshot.rank)
        )).scalars().all()
        return [
            {
                "top_name": r.top_name,
                "rank": r.rank,
                "archive_name": r.archive_name,
                "deal_count": r.deal_count,
                "avg_amount": r.avg_amount,
                "avg_amount_rate": r.avg_amount_rate,
                "min_amount": r.min_amount,
                "market_amount": r.market_amount,
                "market_amount_rate": r.market_amount_rate,
                "deal_amount": r.deal_amount,
            }
            for r in rows
        ]

    # 并发查询
    yesterday_summary = await _fetch_summary(yesterday)
    day_before_summary = await _fetch_summary(day_before)
    top_planes = await _fetch_top_planes(yesterday)
    plane_census = await _fetch_plane_census(yesterday)
    top_census = await _fetch_top_census(yesterday)
    top_archives = await _fetch_top_archives(yesterday)

    return {
        "has_data": yesterday_summary is not None,
        "yesterday": yesterday_summary,
        "day_before": day_before_summary,
        "top_planes": top_planes,
        "plane_census": plane_census,
        "top_census": top_census,
        "top_archives": top_archives,
    }
