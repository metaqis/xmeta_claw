from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database.db import get_db
from app.database.models import Archive, Platform, IP
from app.api.auth import get_current_user

router = APIRouter(prefix="/archives", tags=["藏品"])


class ArchiveItem(BaseModel):
    archive_id: str
    archive_name: str
    total_goods_count: Optional[int] = None
    platform_id: Optional[int] = None
    platform_name: Optional[str] = None
    ip_id: Optional[int] = None
    ip_name: Optional[str] = None
    issue_time: Optional[datetime] = None
    archive_type: Optional[str] = None
    img: Optional[str] = None

    class Config:
        from_attributes = True


class ArchiveListResponse(BaseModel):
    total: int
    items: list[ArchiveItem]


class ArchiveDetailResponse(BaseModel):
    archive_id: str
    archive_name: str
    platform_name: Optional[str] = None
    ip_name: Optional[str] = None
    issue_time: Optional[datetime] = None
    archive_description: Optional[str] = None
    archive_type: Optional[str] = None
    total_goods_count: Optional[int] = None
    is_open_auction: bool = False
    is_open_want_buy: bool = False
    img: Optional[str] = None


@router.get("/", response_model=ArchiveListResponse)
async def get_archives(
    platform_id: Optional[int] = None,
    ip_id: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query(None, description="排序: time_desc, time_asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    query = (
        select(Archive)
        .options(
            selectinload(Archive.platform),
            selectinload(Archive.ip),
        )
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
    if sort_by == "time_asc":
        query = query.order_by(Archive.issue_time.asc().nullslast())
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
            total_goods_count=a.total_goods_count,
            platform_id=a.platform_id,
            platform_name=a.platform.name if a.platform else None,
            ip_id=a.ip_id,
            ip_name=a.ip.ip_name if a.ip else None,
            issue_time=a.issue_time,
            archive_type=a.archive_type,
            img=a.img,
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
        .options(
            selectinload(Archive.platform),
            selectinload(Archive.ip),
        )
        .where(Archive.archive_id == archive_id)
    )
    archive = result.scalar_one_or_none()
    if not archive:
        raise HTTPException(status_code=404, detail="未找到该藏品")
    return ArchiveDetailResponse(
        archive_id=archive.archive_id,
        archive_name=archive.archive_name,
        platform_name=archive.platform.name if archive.platform else None,
        ip_name=archive.ip.ip_name if archive.ip else None,
        issue_time=archive.issue_time,
        archive_description=archive.archive_description,
        archive_type=archive.archive_type,
        total_goods_count=archive.total_goods_count,
        is_open_auction=archive.is_open_auction,
        is_open_want_buy=archive.is_open_want_buy,
        img=archive.img,
    )
