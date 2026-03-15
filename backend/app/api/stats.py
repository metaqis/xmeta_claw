from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date
from pydantic import BaseModel

from app.database.db import get_db
from app.database.models import (
    LaunchCalendar, Archive, IP, Platform
)
from app.api.auth import get_current_user

router = APIRouter(prefix="/stats", tags=["统计"])


class DashboardStats(BaseModel):
    total_archives: int = 0
    total_ips: int = 0
    total_platforms: int = 0
    today_launches: int = 0


class RecentArchiveItem(BaseModel):
    archive_id: str
    archive_name: str
    img: str | None = None


class TopIPItem(BaseModel):
    id: int
    ip_name: str
    archive_count: int = 0


class LaunchTrendItem(BaseModel):
    date: str
    count: int


class DashboardResponse(BaseModel):
    stats: DashboardStats
    recent_archives: list[RecentArchiveItem] = []
    top_ips: list[TopIPItem] = []
    launch_trend: list[LaunchTrendItem] = []


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    # 总计
    total_archives = (await db.execute(select(func.count(Archive.archive_id)))).scalar() or 0
    total_ips = (await db.execute(select(func.count(IP.id)))).scalar() or 0
    total_platforms = (await db.execute(select(func.count(Platform.id)))).scalar() or 0

    # 今日发行
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    today_launches = (await db.execute(
        select(func.count(LaunchCalendar.id)).where(
            LaunchCalendar.sell_time.between(today, tomorrow)
        )
    )).scalar() or 0

    stats = DashboardStats(
        total_archives=total_archives,
        total_ips=total_ips,
        total_platforms=total_platforms,
        today_launches=today_launches,
    )

    recent_result = await db.execute(
        select(Archive)
        .order_by(Archive.issue_time.desc().nullslast())
        .limit(10)
    )
    recent_archives = [
        RecentArchiveItem(
            archive_id=a.archive_id,
            archive_name=a.archive_name,
            img=a.img,
        )
        for a in recent_result.scalars().all()
    ]

    # 热门IP
    ip_result = await db.execute(
        select(IP, func.count(Archive.archive_id).label("cnt"))
        .outerjoin(Archive, Archive.ip_id == IP.id)
        .group_by(IP.id)
        .order_by(func.count(Archive.archive_id).desc())
        .limit(10)
    )
    top_ips = [
        TopIPItem(id=row[0].id, ip_name=row[0].ip_name, archive_count=row[1])
        for row in ip_result.all()
    ]

    # 近30天发行趋势
    thirty_days_ago = today - timedelta(days=30)
    trend_result = await db.execute(
        select(
            cast(LaunchCalendar.sell_time, Date).label("date"),
            func.count(LaunchCalendar.id).label("cnt"),
        )
        .where(LaunchCalendar.sell_time >= thirty_days_ago)
        .where(LaunchCalendar.sell_time < tomorrow)
        .group_by(cast(LaunchCalendar.sell_time, Date))
        .order_by(cast(LaunchCalendar.sell_time, Date))
    )
    launch_trend = [
        LaunchTrendItem(date=str(row[0]), count=row[1])
        for row in trend_result.all()
    ]

    return DashboardResponse(
        stats=stats,
        recent_archives=recent_archives,
        top_ips=top_ips,
        launch_trend=launch_trend,
    )
