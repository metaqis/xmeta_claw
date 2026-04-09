"""日报数据获取 — 汇总当日发行数据、增强含品信息、IP深度画像。"""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LaunchCalendar, IP
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
    }
