from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.database.db import get_db
from app.database.models import LaunchCalendar, LaunchDetail, Platform, IP
from app.api.auth import get_current_user

router = APIRouter(prefix="/calendar", tags=["发行日历"])


class CalendarItem(BaseModel):
    id: int
    name: str
    sell_time: Optional[datetime] = None
    price: Optional[float] = None
    count: Optional[int] = None
    platform_id: Optional[int] = None
    platform_name: Optional[str] = None
    ip_id: Optional[int] = None
    ip_name: Optional[str] = None
    img: Optional[str] = None
    priority_purchase_num: Optional[int] = None
    is_priority_purchase: bool = False
    source_id: Optional[str] = None

    class Config:
        from_attributes = True


class CalendarListResponse(BaseModel):
    total: int
    items: list[CalendarItem]


class CalendarDetailResponse(BaseModel):
    id: int
    name: str
    sell_time: Optional[datetime] = None
    price: Optional[float] = None
    count: Optional[int] = None
    platform_name: Optional[str] = None
    ip_name: Optional[str] = None
    img: Optional[str] = None
    priority_purchase_time: Optional[datetime] = None
    context_condition: Optional[str] = None
    status: Optional[str] = None
    raw_json: Optional[str] = None


@router.get("/", response_model=CalendarListResponse)
async def get_calendar(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD"),
    platform_id: Optional[int] = None,
    ip_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    query = select(LaunchCalendar).outerjoin(Platform).outerjoin(IP)
    count_query = select(func.count(LaunchCalendar.id))

    if date:
        dt = datetime.strptime(date, "%Y-%m-%d")
        day_start = dt.replace(hour=0, minute=0, second=0)
        day_end = dt.replace(hour=23, minute=59, second=59)
        query = query.where(LaunchCalendar.sell_time.between(day_start, day_end))
        count_query = count_query.where(LaunchCalendar.sell_time.between(day_start, day_end))

    if platform_id:
        query = query.where(LaunchCalendar.platform_id == platform_id)
        count_query = count_query.where(LaunchCalendar.platform_id == platform_id)

    if ip_id:
        query = query.where(LaunchCalendar.ip_id == ip_id)
        count_query = count_query.where(LaunchCalendar.ip_id == ip_id)

    if search:
        query = query.where(LaunchCalendar.name.ilike(f"%{search}%"))
        count_query = count_query.where(LaunchCalendar.name.ilike(f"%{search}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(LaunchCalendar.sell_time.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    calendars = result.scalars().all()

    items = []
    for c in calendars:
        item = CalendarItem(
            id=c.id,
            name=c.name,
            sell_time=c.sell_time,
            price=c.price,
            count=c.count,
            platform_id=c.platform_id,
            platform_name=c.platform.name if c.platform else None,
            ip_id=c.ip_id,
            ip_name=c.ip.ip_name if c.ip else None,
            img=c.img,
            priority_purchase_num=c.priority_purchase_num,
            is_priority_purchase=c.is_priority_purchase,
            source_id=c.source_id,
        )
        items.append(item)

    return CalendarListResponse(total=total, items=items)


@router.get("/{calendar_id}", response_model=CalendarDetailResponse)
async def get_calendar_detail(
    calendar_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await db.execute(
        select(LaunchCalendar)
        .outerjoin(Platform)
        .outerjoin(IP)
        .where(LaunchCalendar.id == calendar_id)
    )
    cal = result.scalar_one_or_none()
    if not cal:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="未找到该发行记录")

    detail_result = await db.execute(
        select(LaunchDetail).where(LaunchDetail.launch_id == cal.id)
    )
    detail = detail_result.scalar_one_or_none()

    return CalendarDetailResponse(
        id=cal.id,
        name=cal.name,
        sell_time=cal.sell_time,
        price=cal.price,
        count=cal.count,
        platform_name=cal.platform.name if cal.platform else None,
        ip_name=cal.ip.ip_name if cal.ip else None,
        img=cal.img,
        priority_purchase_time=detail.priority_purchase_time if detail else None,
        context_condition=detail.context_condition if detail else None,
        status=detail.status if detail else None,
        raw_json=detail.raw_json if detail else None,
    )
