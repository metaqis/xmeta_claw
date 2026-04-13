"""Dashboard 聚合接口 — 为首页提供日历 + 藏品 + 市场趋势数据"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database.db import get_db
from app.database.models import (
    Archive,
    IP,
    LaunchCalendar,
    MarketDailySummary,
    MarketIPSnapshot,
    MarketPlaneSnapshot,
    Platform,
)

router = APIRouter(prefix="/stats", tags=["统计"])


# ── 响应模型 ─────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_archives: int = 0
    total_ips: int = 0
    total_platforms: int = 0
    today_launches: int = 0


class CalendarCardItem(BaseModel):
    id: int
    name: str
    sell_time: Optional[datetime] = None
    price: Optional[float] = None
    count: Optional[int] = None
    platform_name: Optional[str] = None
    ip_name: Optional[str] = None
    img: Optional[str] = None


class RecentArchiveItem(BaseModel):
    archive_id: str
    archive_name: str
    img: Optional[str] = None
    issue_time: Optional[datetime] = None
    ip_name: Optional[str] = None


class TrendPoint(BaseModel):
    date: str
    value: Optional[float] = None


class PlaneTrendItem(BaseModel):
    plane_code: str
    plane_name: str
    points: list[TrendPoint] = []


class IPTrendItem(BaseModel):
    community_ip_id: int
    name: str
    points: list[TrendPoint] = []


class DashboardResponse(BaseModel):
    stats: DashboardStats
    today_calendar: list[CalendarCardItem] = []
    recent_archives: list[RecentArchiveItem] = []
    market_value_trend: list[TrendPoint] = []
    deal_count_trend: list[TrendPoint] = []
    plane_trends: list[PlaneTrendItem] = []
    ip_trends: list[IPTrendItem] = []


# ── 接口 ─────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    days: int = Query(7, ge=7, le=90, description="趋势天数: 7 / 30 / 90"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    today_date = now.date()
    start_date = (now - timedelta(days=days)).date()

    # ── 基本统计 ──
    total_archives = (await db.execute(select(func.count(Archive.archive_id)))).scalar() or 0
    total_ips = (await db.execute(select(func.count(IP.id)))).scalar() or 0
    total_platforms = (await db.execute(select(func.count(Platform.id)))).scalar() or 0

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today_start + timedelta(days=1)
    today_launches = (await db.execute(
        select(func.count(LaunchCalendar.id)).where(
            LaunchCalendar.sell_time.between(today_start, tomorrow)
        )
    )).scalar() or 0

    stats = DashboardStats(
        total_archives=total_archives,
        total_ips=total_ips,
        total_platforms=total_platforms,
        today_launches=today_launches,
    )

    # ── 今日发售日历 ──
    cal_result = await db.execute(
        select(LaunchCalendar)
        .options(selectinload(LaunchCalendar.platform), selectinload(LaunchCalendar.ip))
        .where(LaunchCalendar.sell_time.between(today_start, tomorrow))
        .order_by(LaunchCalendar.sell_time.asc())
    )
    today_calendar = [
        CalendarCardItem(
            id=c.id,
            name=c.name,
            sell_time=c.sell_time,
            price=c.price,
            count=c.count,
            platform_name=c.platform.name if c.platform else None,
            ip_name=c.ip.ip_name if c.ip else None,
            img=c.img,
        )
        for c in cal_result.scalars().all()
    ]

    # ── 最近更新藏品 ──
    recent_result = await db.execute(
        select(Archive)
        .options(selectinload(Archive.ip))
        .order_by(Archive.updated_at.desc().nullslast())
        .limit(10)
    )
    recent_archives = [
        RecentArchiveItem(
            archive_id=a.archive_id,
            archive_name=a.archive_name,
            img=a.img,
            issue_time=a.issue_time,
            ip_name=a.ip.ip_name if a.ip else None,
        )
        for a in recent_result.scalars().all()
    ]

    # ── 全市场市值 + 成交量趋势 ──
    summary_result = await db.execute(
        select(MarketDailySummary)
        .where(MarketDailySummary.stat_date >= start_date)
        .order_by(MarketDailySummary.stat_date.asc())
    )
    summaries = summary_result.scalars().all()
    market_value_trend = [
        TrendPoint(date=str(s.stat_date), value=s.total_market_value)
        for s in summaries
    ]
    deal_count_trend = [
        TrendPoint(date=str(s.stat_date), value=float(s.total_deal_count) if s.total_deal_count else None)
        for s in summaries
    ]

    # ── 板块市值趋势（Top 6）──
    latest_plane_date = (await db.execute(
        select(func.max(MarketPlaneSnapshot.stat_date))
    )).scalar()

    plane_trends: list[PlaneTrendItem] = []
    if latest_plane_date:
        top_planes_result = await db.execute(
            select(MarketPlaneSnapshot.plane_code, MarketPlaneSnapshot.plane_name)
            .where(MarketPlaneSnapshot.stat_date == latest_plane_date)
            .order_by(MarketPlaneSnapshot.total_market_value.desc().nullslast())
            .limit(6)
        )
        top_planes = top_planes_result.all()
        top_plane_codes = [r[0] for r in top_planes]
        plane_name_map = {r[0]: r[1] for r in top_planes}

        if top_plane_codes:
            plane_data = await db.execute(
                select(MarketPlaneSnapshot)
                .where(
                    MarketPlaneSnapshot.stat_date >= start_date,
                    MarketPlaneSnapshot.plane_code.in_(top_plane_codes),
                )
                .order_by(MarketPlaneSnapshot.stat_date.asc())
            )
            grouped: dict[str, list[TrendPoint]] = {c: [] for c in top_plane_codes}
            for row in plane_data.scalars().all():
                if row.plane_code in grouped:
                    grouped[row.plane_code].append(
                        TrendPoint(date=str(row.stat_date), value=row.total_market_value)
                    )
            plane_trends = [
                PlaneTrendItem(
                    plane_code=code,
                    plane_name=plane_name_map.get(code, code),
                    points=grouped[code],
                )
                for code in top_plane_codes
            ]

    # ── 热门 IP 市值趋势（Top 6）──
    latest_ip_date = (await db.execute(
        select(func.max(MarketIPSnapshot.stat_date))
    )).scalar()

    ip_trends: list[IPTrendItem] = []
    if latest_ip_date:
        top_ips_result = await db.execute(
            select(MarketIPSnapshot.community_ip_id, MarketIPSnapshot.name)
            .where(MarketIPSnapshot.stat_date == latest_ip_date)
            .order_by(MarketIPSnapshot.market_amount.desc().nullslast())
            .limit(6)
        )
        top_ips = top_ips_result.all()
        top_ip_ids = [r[0] for r in top_ips]
        ip_name_map = {r[0]: r[1] for r in top_ips}

        if top_ip_ids:
            ip_data = await db.execute(
                select(MarketIPSnapshot)
                .where(
                    MarketIPSnapshot.stat_date >= start_date,
                    MarketIPSnapshot.community_ip_id.in_(top_ip_ids),
                )
                .order_by(MarketIPSnapshot.stat_date.asc())
            )
            ip_grouped: dict[int, list[TrendPoint]] = {i: [] for i in top_ip_ids}
            for row in ip_data.scalars().all():
                if row.community_ip_id in ip_grouped:
                    ip_grouped[row.community_ip_id].append(
                        TrendPoint(date=str(row.stat_date), value=row.market_amount)
                    )
            ip_trends = [
                IPTrendItem(
                    community_ip_id=ip_id,
                    name=ip_name_map.get(ip_id, str(ip_id)),
                    points=ip_grouped[ip_id],
                )
                for ip_id in top_ip_ids
            ]

    return DashboardResponse(
        stats=stats,
        today_calendar=today_calendar,
        recent_archives=recent_archives,
        market_value_trend=market_value_trend,
        deal_count_trend=deal_count_trend,
        plane_trends=plane_trends,
        ip_trends=ip_trends,
    )

