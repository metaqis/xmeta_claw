from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database.db import get_db
from app.database.models import IP, Platform, Archive
from app.api.auth import get_current_user

router = APIRouter(prefix="/ips", tags=["IP"])


class IPItem(BaseModel):
    id: int
    ip_name: str
    ip_avatar: Optional[str] = None
    fans_count: Optional[int] = None
    platform_id: Optional[int] = None
    platform_name: Optional[str] = None
    archive_count: int = 0

    class Config:
        from_attributes = True


class IPListResponse(BaseModel):
    total: int
    items: list[IPItem]


@router.get("/", response_model=IPListResponse)
async def get_ips(
    platform_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    query = (
        select(
            IP,
            func.count(Archive.archive_id).label("archive_count"),
        )
        .options(selectinload(IP.platform))
        .outerjoin(Platform, IP.platform_id == Platform.id)
        .outerjoin(Archive, Archive.ip_id == IP.id)
        .group_by(IP.id, Platform.id)
    )
    count_query = select(func.count(func.distinct(IP.id)))

    if platform_id:
        query = query.where(IP.platform_id == platform_id)
        count_query = count_query.where(IP.platform_id == platform_id)
    if search:
        query = query.where(IP.ip_name.ilike(f"%{search}%"))
        count_query = count_query.where(IP.ip_name.ilike(f"%{search}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(func.count(Archive.archive_id).desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        ip_obj = row[0]
        archive_count = row[1]
        items.append(IPItem(
            id=ip_obj.id,
            ip_name=ip_obj.ip_name,
            ip_avatar=ip_obj.ip_avatar,
            fans_count=ip_obj.fans_count,
            platform_id=ip_obj.platform_id,
            platform_name=ip_obj.platform.name if ip_obj.platform else None,
            archive_count=archive_count,
        ))

    return IPListResponse(total=total, items=items)
