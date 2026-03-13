from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.database.db import get_db
from app.database.models import Archive, ArchiveMarket, ArchivePriceHistory, Platform, IP
from app.api.auth import get_current_user

router = APIRouter(prefix="/archives", tags=["藏品"])


class ArchiveItem(BaseModel):
    archive_id: str
    archive_name: str
    platform_id: Optional[int] = None
    platform_name: Optional[str] = None
    ip_id: Optional[int] = None
    ip_name: Optional[str] = None
    issue_time: Optional[datetime] = None
    archive_type: Optional[str] = None
    is_hot: bool = False
    img: Optional[str] = None
    goods_min_price: Optional[float] = None
    selling_count: Optional[int] = None
    deal_count: Optional[int] = None

    class Config:
        from_attributes = True


class ArchiveListResponse(BaseModel):
    total: int
    items: list[ArchiveItem]


class PriceHistoryItem(BaseModel):
    min_price: Optional[float] = None
    sell_count: int = 0
    buy_count: int = 0
    deal_count: int = 0
    record_time: Optional[datetime] = None


class ArchiveDetailResponse(BaseModel):
    archive_id: str
    archive_name: str
    platform_name: Optional[str] = None
    ip_name: Optional[str] = None
    issue_time: Optional[datetime] = None
    archive_description: Optional[str] = None
    archive_type: Optional[str] = None
    is_hot: bool = False
    is_open_auction: bool = False
    is_open_want_buy: bool = False
    img: Optional[str] = None
    goods_min_price: Optional[float] = None
    want_buy_count: int = 0
    selling_count: int = 0
    deal_count: int = 0
    want_buy_max_price: Optional[float] = None
    deal_price: Optional[float] = None
    price_history: list[PriceHistoryItem] = []


@router.get("/", response_model=ArchiveListResponse)
async def get_archives(
    platform_id: Optional[int] = None,
    ip_id: Optional[int] = None,
    search: Optional[str] = None,
    is_hot: Optional[bool] = None,
    sort_by: Optional[str] = Query(None, description="排序: price_asc, price_desc, time_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    query = (
        select(Archive)
        .outerjoin(Platform, Archive.platform_id == Platform.id)
        .outerjoin(IP, Archive.ip_id == IP.id)
        .outerjoin(ArchiveMarket, Archive.archive_id == ArchiveMarket.archive_id)
    )
    count_query = select(func.count(Archive.archive_id))

    if platform_id:
        query = query.where(Archive.platform_id == platform_id)
        count_query = count_query.where(Archive.platform_id == platform_id)
    if ip_id:
        query = query.where(Archive.ip_id == ip_id)
        count_query = count_query.where(Archive.ip_id == ip_id)
    if search:
        query = query.where(Archive.archive_name.ilike(f"%{search}%"))
        count_query = count_query.where(Archive.archive_name.ilike(f"%{search}%"))
    if is_hot is not None:
        query = query.where(Archive.is_hot == is_hot)
        count_query = count_query.where(Archive.is_hot == is_hot)

    if sort_by == "price_asc":
        query = query.order_by(ArchiveMarket.goods_min_price.asc().nullslast())
    elif sort_by == "price_desc":
        query = query.order_by(ArchiveMarket.goods_min_price.desc().nullslast())
    else:
        query = query.order_by(Archive.issue_time.desc().nullslast())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    archives = result.scalars().unique().all()

    items = []
    for a in archives:
        items.append(ArchiveItem(
            archive_id=a.archive_id,
            archive_name=a.archive_name,
            platform_id=a.platform_id,
            platform_name=a.platform.name if a.platform else None,
            ip_id=a.ip_id,
            ip_name=a.ip.ip_name if a.ip else None,
            issue_time=a.issue_time,
            archive_type=a.archive_type,
            is_hot=a.is_hot,
            img=a.img,
            goods_min_price=a.market.goods_min_price if a.market else None,
            selling_count=a.market.selling_count if a.market else None,
            deal_count=a.market.deal_count if a.market else None,
        ))

    return ArchiveListResponse(total=total, items=items)


@router.get("/{archive_id}", response_model=ArchiveDetailResponse)
async def get_archive_detail(
    archive_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await db.execute(
        select(Archive)
        .outerjoin(Platform)
        .outerjoin(IP)
        .outerjoin(ArchiveMarket)
        .where(Archive.archive_id == archive_id)
    )
    archive = result.scalar_one_or_none()
    if not archive:
        raise HTTPException(status_code=404, detail="未找到该藏品")

    history_result = await db.execute(
        select(ArchivePriceHistory)
        .where(ArchivePriceHistory.archive_id == archive_id)
        .order_by(ArchivePriceHistory.record_time.asc())
        .limit(500)
    )
    history = history_result.scalars().all()

    market = archive.market
    return ArchiveDetailResponse(
        archive_id=archive.archive_id,
        archive_name=archive.archive_name,
        platform_name=archive.platform.name if archive.platform else None,
        ip_name=archive.ip.ip_name if archive.ip else None,
        issue_time=archive.issue_time,
        archive_description=archive.archive_description,
        archive_type=archive.archive_type,
        is_hot=archive.is_hot,
        is_open_auction=archive.is_open_auction,
        is_open_want_buy=archive.is_open_want_buy,
        img=archive.img,
        goods_min_price=market.goods_min_price if market else None,
        want_buy_count=market.want_buy_count if market else 0,
        selling_count=market.selling_count if market else 0,
        deal_count=market.deal_count if market else 0,
        want_buy_max_price=market.want_buy_max_price if market else None,
        deal_price=market.deal_price if market else None,
        price_history=[
            PriceHistoryItem(
                min_price=h.min_price,
                sell_count=h.sell_count,
                buy_count=h.buy_count,
                deal_count=h.deal_count,
                record_time=h.record_time,
            )
            for h in history
        ],
    )
