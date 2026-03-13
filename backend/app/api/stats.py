from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.database.db import get_db
from app.database.models import (
    LaunchCalendar, Archive, ArchiveMarket, IP, Platform
)
from app.api.auth import get_current_user

router = APIRouter(prefix="/stats", tags=["统计"])


class DashboardStats(BaseModel):
    total_archives: int = 0
    total_ips: int = 0
    total_platforms: int = 0
    today_launches: int = 0
    hot_archives: int = 0


class TopArchiveItem(BaseModel):
    archive_id: str
    archive_name: str
    goods_min_price: float | None = None
    img: str | None = None


class TopIPItem(BaseModel):
    id: int
    ip_name: str
    archive_count: int = 0


class DashboardResponse(BaseModel):
    stats: DashboardStats
    top_price_archives: list[TopArchiveItem] = []
    top_ips: list[TopIPItem] = []


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    # 总计
    total_archives = (await db.execute(select(func.count(Archive.archive_id)))).scalar() or 0
    total_ips = (await db.execute(select(func.count(IP.id)))).scalar() or 0
    total_platforms = (await db.execute(select(func.count(Platform.id)))).scalar() or 0
    hot_archives = (await db.execute(
        select(func.count(Archive.archive_id)).where(Archive.is_hot == True)
    )).scalar() or 0

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
        hot_archives=hot_archives,
    )

    # 价格排行
    price_result = await db.execute(
        select(Archive, ArchiveMarket.goods_min_price)
        .join(ArchiveMarket, Archive.archive_id == ArchiveMarket.archive_id)
        .where(ArchiveMarket.goods_min_price.isnot(None))
        .order_by(ArchiveMarket.goods_min_price.desc())
        .limit(10)
    )
    top_price = [
        TopArchiveItem(
            archive_id=row[0].archive_id,
            archive_name=row[0].archive_name,
            goods_min_price=row[1],
            img=row[0].img,
        )
        for row in price_result.all()
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

    return DashboardResponse(stats=stats, top_price_archives=top_price, top_ips=top_ips)
