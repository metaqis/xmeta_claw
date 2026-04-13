"""市场每日快照数据接口"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.db import get_db
from app.database.models import (
    MarketDailySummary,
    MarketPlaneSnapshot,
    MarketIPSnapshot,
    MarketArchiveSnapshot,
    MarketPlaneCensus,
    MarketTopCensus,
)

router = APIRouter(prefix="/market-stats", tags=["市场统计"])


# ── Pydantic 响应模型 ──────────────────────────────────────────────

class DailySummaryItem(BaseModel):
    stat_date: str
    total_deal_count: Optional[int] = None
    total_market_value: Optional[float] = None
    total_deal_amount: Optional[float] = None
    active_plane_count: Optional[int] = None
    top_plane_name: Optional[str] = None
    top_plane_deal_count: Optional[int] = None
    top_ip_name: Optional[str] = None
    top_ip_deal_count: Optional[int] = None


class PlaneSnapshotItem(BaseModel):
    stat_date: str
    plane_code: str
    plane_name: str
    avg_price: Optional[float] = None       # 均价涨跌幅 %
    deal_price: Optional[float] = None
    deal_count: Optional[int] = None
    shelves_rate: Optional[float] = None
    total_market_value: Optional[float] = None


class IPSnapshotItem(BaseModel):
    stat_date: str
    community_ip_id: int
    name: str
    avatar: Optional[str] = None
    rank: Optional[int] = None
    archive_count: Optional[int] = None
    market_amount: Optional[float] = None
    market_amount_rate: Optional[float] = None
    hot: Optional[float] = None
    hot_rate: Optional[float] = None
    avg_amount: Optional[float] = None
    avg_amount_rate: Optional[float] = None
    deal_count: Optional[int] = None
    deal_count_rate: Optional[float] = None
    publish_count: Optional[int] = None


class ArchiveSnapshotItem(BaseModel):
    stat_date: str
    top_code: str
    top_name: str
    rank: int
    archive_id: int
    archive_name: Optional[str] = None
    archive_img: Optional[str] = None
    selling_count: Optional[int] = None
    deal_count: Optional[int] = None
    market_amount: Optional[float] = None
    market_amount_rate: Optional[float] = None
    min_amount: Optional[float] = None
    min_amount_rate: Optional[float] = None
    avg_amount: Optional[float] = None
    avg_amount_rate: Optional[float] = None
    up_rate: Optional[float] = None
    deal_amount: Optional[float] = None
    deal_amount_rate: Optional[float] = None
    publish_count: Optional[int] = None
    is_transfer: Optional[bool] = None


class TopCategory(BaseModel):
    code: str
    name: str


class UpDownBucket(BaseModel):
    label: str
    count: int
    type: int  # 1=涨 2=跌


class PlaneCensusItem(BaseModel):
    stat_date: str
    plane_code: str
    plane_name: Optional[str] = None
    total_market_amount: Optional[float] = None
    total_market_amount_rate: Optional[float] = None
    total_deal_count: Optional[int] = None
    total_deal_count_rate: Optional[float] = None
    total_archive_count: Optional[int] = None
    up_archive_count: Optional[int] = None
    down_archive_count: Optional[int] = None
    up_down_list: list[UpDownBucket] = []


class TopCensusItem(BaseModel):
    stat_date: str
    top_code: str
    top_name: Optional[str] = None
    total_market_amount: Optional[float] = None
    total_market_amount_rate: Optional[float] = None
    total_deal_count: Optional[int] = None
    total_deal_count_rate: Optional[float] = None
    total_archive_count: Optional[int] = None
    up_archive_count: Optional[int] = None
    down_archive_count: Optional[int] = None
    up_down_list: list[UpDownBucket] = []


class AvailableDatesResponse(BaseModel):
    dates: list[str]


# ── 工具函数 ───────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str], default: date) -> date:
    if not date_str:
        return default
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"日期格式错误: {date_str}，请使用 YYYY-MM-DD")


# ── 接口 ───────────────────────────────────────────────────────────

@router.get("/available-dates", response_model=AvailableDatesResponse)
async def get_available_dates(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """获取已有快照数据的日期列表"""
    result = await db.execute(
        select(MarketDailySummary.stat_date).order_by(MarketDailySummary.stat_date.desc())
    )
    rows = result.scalars().all()
    return AvailableDatesResponse(dates=[str(r) for r in rows])


@router.get("/summary", response_model=list[DailySummaryItem])
async def get_daily_summaries(
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD（默认近30天）"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（默认今天）"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """查询全市场每日汇总趋势（用于折线图）"""
    today = datetime.now(timezone.utc).date()
    end_date = _parse_date(end, today)
    start_date = _parse_date(start, today - timedelta(days=29))

    result = await db.execute(
        select(MarketDailySummary)
        .where(MarketDailySummary.stat_date.between(start_date, end_date))
        .order_by(MarketDailySummary.stat_date.asc())
    )
    rows = result.scalars().all()
    return [
        DailySummaryItem(
            stat_date=str(r.stat_date),
            total_deal_count=r.total_deal_count,
            total_market_value=r.total_market_value,
            total_deal_amount=r.total_deal_amount,
            active_plane_count=r.active_plane_count,
            top_plane_name=r.top_plane_name,
            top_plane_deal_count=r.top_plane_deal_count,
            top_ip_name=r.top_ip_name,
            top_ip_deal_count=r.top_ip_deal_count,
        )
        for r in rows
    ]


@router.get("/planes", response_model=list[PlaneSnapshotItem])
async def get_plane_snapshots(
    date: Optional[str] = Query(None, description="查询日期 YYYY-MM-DD（默认最新一天）"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """查询某天各板块市场快照"""
    if date:
        stat_date = _parse_date(date, None)
    else:
        latest = (await db.execute(
            select(func.max(MarketPlaneSnapshot.stat_date))
        )).scalar()
        if not latest:
            return []
        stat_date = latest

    result = await db.execute(
        select(MarketPlaneSnapshot)
        .where(MarketPlaneSnapshot.stat_date == stat_date)
        .order_by(MarketPlaneSnapshot.total_market_value.desc().nullslast())
    )
    rows = result.scalars().all()
    return [
        PlaneSnapshotItem(
            stat_date=str(r.stat_date),
            plane_code=r.plane_code,
            plane_name=r.plane_name,
            avg_price=r.avg_price,
            deal_price=r.deal_price,
            deal_count=r.deal_count,
            shelves_rate=r.shelves_rate,
            total_market_value=r.total_market_value,
        )
        for r in rows
    ]


@router.get("/ips", response_model=list[IPSnapshotItem])
async def get_ip_snapshots(
    date: Optional[str] = Query(None, description="查询日期 YYYY-MM-DD（默认最新一天）"),
    limit: int = Query(20, ge=1, le=50, description="返回条数上限"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """查询某天 IP 市场排行榜"""
    if date:
        stat_date = _parse_date(date, None)
    else:
        latest = (await db.execute(
            select(func.max(MarketIPSnapshot.stat_date))
        )).scalar()
        if not latest:
            return []
        stat_date = latest

    result = await db.execute(
        select(MarketIPSnapshot)
        .where(MarketIPSnapshot.stat_date == stat_date)
        .order_by(MarketIPSnapshot.rank.asc().nullslast())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        IPSnapshotItem(
            stat_date=str(r.stat_date),
            community_ip_id=r.community_ip_id,
            name=r.name,
            avatar=r.avatar,
            rank=r.rank,
            archive_count=r.archive_count,
            market_amount=r.market_amount,
            market_amount_rate=r.market_amount_rate,
            hot=r.hot,
            hot_rate=r.hot_rate,
            avg_amount=r.avg_amount,
            avg_amount_rate=r.avg_amount_rate,
            deal_count=r.deal_count,
            deal_count_rate=r.deal_count_rate,
            publish_count=r.publish_count,
        )
        for r in rows
    ]


@router.get("/archives", response_model=list[ArchiveSnapshotItem])
async def get_archive_snapshots(
    date: Optional[str] = Query(None, description="查询日期 YYYY-MM-DD（默认最新一天）"),
    top_code: Optional[str] = Query(None, description="行情分类编码，不传则返回全部分类"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """查询某天某分类下热门藏品排名"""
    if date:
        stat_date = _parse_date(date, None)
    else:
        latest = (await db.execute(
            select(func.max(MarketArchiveSnapshot.stat_date))
        )).scalar()
        if not latest:
            return []
        stat_date = latest

    stmt = (
        select(MarketArchiveSnapshot)
        .where(MarketArchiveSnapshot.stat_date == stat_date)
        .order_by(
            MarketArchiveSnapshot.top_code.asc(),
            MarketArchiveSnapshot.rank.asc(),
        )
    )
    if top_code:
        stmt = stmt.where(MarketArchiveSnapshot.top_code == top_code)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        ArchiveSnapshotItem(
            stat_date=str(r.stat_date),
            top_code=r.top_code,
            top_name=r.top_name,
            rank=r.rank,
            archive_id=r.archive_id,
            archive_name=r.archive_name,
            archive_img=r.archive_img,
            selling_count=r.selling_count,
            deal_count=r.deal_count,
            market_amount=r.market_amount,
            market_amount_rate=r.market_amount_rate,
            min_amount=r.min_amount,
            min_amount_rate=r.min_amount_rate,
            avg_amount=r.avg_amount,
            avg_amount_rate=r.avg_amount_rate,
            up_rate=r.up_rate,
            deal_amount=r.deal_amount,
            deal_amount_rate=r.deal_amount_rate,
            publish_count=r.publish_count,
            is_transfer=r.is_transfer,
        )
        for r in rows
    ]


@router.get("/top-categories", response_model=list[dict])
async def get_top_categories(
    date: Optional[str] = Query(None, description="查询日期 YYYY-MM-DD（默认最新一天）"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """获取某天已有数据的行情分类列表"""
    if date:
        stat_date = _parse_date(date, None)
    else:
        latest = (await db.execute(
            select(func.max(MarketArchiveSnapshot.stat_date))
        )).scalar()
        if not latest:
            return []
        stat_date = latest

    result = await db.execute(
        select(
            MarketArchiveSnapshot.top_code,
            MarketArchiveSnapshot.top_name,
        )
        .where(MarketArchiveSnapshot.stat_date == stat_date)
        .distinct()
        .order_by(MarketArchiveSnapshot.top_code)
    )
    return [{"code": r.top_code, "name": r.top_name} for r in result.all()]


def _parse_census_row(r: MarketPlaneCensus | MarketTopCensus, code_key: str, name_key: str) -> dict:
    try:
        up_down = json.loads(r.up_down_json or "[]")
    except Exception:
        up_down = []
    return {
        "stat_date": str(r.stat_date),
        code_key: getattr(r, code_key),
        name_key: getattr(r, name_key),
        "total_market_amount": r.total_market_amount,
        "total_market_amount_rate": r.total_market_amount_rate,
        "total_deal_count": r.total_deal_count,
        "total_deal_count_rate": r.total_deal_count_rate,
        "total_archive_count": r.total_archive_count,
        "up_archive_count": r.up_archive_count,
        "down_archive_count": r.down_archive_count,
        "up_down_list": up_down,
    }


@router.get("/plane-census", response_model=list[PlaneCensusItem])
async def get_plane_census(
    date: Optional[str] = Query(None, description="查询日期 YYYY-MM-DD（默认最新一天）"),
    plane_code: Optional[str] = Query(None, description="板块编码，不传则返回全部板块"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """查询某天各板块涨跌分布普查数据"""
    if date:
        stat_date = _parse_date(date, None)
    else:
        latest = (await db.execute(
            select(func.max(MarketPlaneCensus.stat_date))
        )).scalar()
        if not latest:
            return []
        stat_date = latest

    stmt = (
        select(MarketPlaneCensus)
        .where(MarketPlaneCensus.stat_date == stat_date)
        .order_by(MarketPlaneCensus.total_deal_count.desc().nullslast())
    )
    if plane_code:
        stmt = stmt.where(MarketPlaneCensus.plane_code == plane_code)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        PlaneCensusItem(**_parse_census_row(r, "plane_code", "plane_name"))
        for r in rows
    ]


@router.get("/top-census", response_model=list[TopCensusItem])
async def get_top_census(
    date: Optional[str] = Query(None, description="查询日期 YYYY-MM-DD（默认最新一天）"),
    top_code: Optional[str] = Query(None, description="行情分类编码，不传则返回全部分类"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """查询某天各行情分类涨跌分布普查数据"""
    if date:
        stat_date = _parse_date(date, None)
    else:
        latest = (await db.execute(
            select(func.max(MarketTopCensus.stat_date))
        )).scalar()
        if not latest:
            return []
        stat_date = latest

    stmt = (
        select(MarketTopCensus)
        .where(MarketTopCensus.stat_date == stat_date)
        .order_by(MarketTopCensus.total_deal_count.desc().nullslast())
    )
    if top_code:
        stmt = stmt.where(MarketTopCensus.top_code == top_code)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        TopCensusItem(**_parse_census_row(r, "top_code", "top_name"))
        for r in rows
    ]

