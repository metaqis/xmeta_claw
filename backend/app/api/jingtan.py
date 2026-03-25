from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.auth import get_current_user, require_admin
from app.core.config import get_settings
from app.crawler.antfans_client import antfans_client
from app.database.db import get_db
from app.database.models import JingtanSkuHomepageDetail, JingtanSkuWiki
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()

router = APIRouter(prefix="/jingtan", tags=["鲸探"])


class SkuWikiListQuery(BaseModel):
    pageNum: int = 1
    pageSize: int = 20


class AntFansProxyResponse(BaseModel):
    status: int
    data: Optional[Any] = None
    text: str = ""


@router.post("/sku-wiki-list", response_model=AntFansProxyResponse)
async def sku_wiki_list(
    req: list[SkuWikiListQuery],
    _admin=Depends(require_admin),
):
    payload_obj = [req[0].model_dump()] if req else [{"pageNum": 1, "pageSize": 20}]
    result = await antfans_client.post_mgw_safe(
        operation_type=settings.ANTFANS_OPERATION_TYPE_QUERY_SKU_WIKI,
        payload_obj=payload_obj,
    )
    return AntFansProxyResponse(status=result["status"], data=result["json"], text=result["text"])


class JingtanSkuWikiItem(BaseModel):
    sku_id: str
    sku_name: str
    author: Optional[str] = None
    owner: Optional[str] = None
    partner: Optional[str] = None
    partner_name: Optional[str] = None
    first_category: Optional[str] = None
    first_category_name: Optional[str] = None
    second_category: Optional[str] = None
    second_category_name: Optional[str] = None
    quantity_type: Optional[str] = None
    sku_quantity: Optional[int] = None
    sku_type: Optional[str] = None
    sku_issue_time_ms: Optional[int] = None
    sku_producer: Optional[str] = None
    mini_file_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JingtanSkuWikiListResponse(BaseModel):
    total: int
    items: list[JingtanSkuWikiItem]


class JingtanSkuHomepageDetailItem(BaseModel):
    sku_id: str
    sku_name: str
    author: Optional[str] = None
    owner: Optional[str] = None
    partner: Optional[str] = None
    partner_name: Optional[str] = None
    biz_type: Optional[str] = None
    bg_conf: Optional[str] = None
    bg_info: Optional[str] = None
    has_item: Optional[bool] = None
    mini_file_url: Optional[str] = None
    origin_file_url: Optional[str] = None
    quantity_type: Optional[str] = None
    sku_desc: Optional[str] = None
    sku_desc_image_file_ids: Optional[str] = None
    sku_issue_time_ms: Optional[int] = None
    sku_producer: Optional[str] = None
    sku_quantity: Optional[int] = None
    sku_type: Optional[str] = None
    collect_num: Optional[int] = None
    user_collect_status: Optional[bool] = None
    comment_num: Optional[int] = None
    mini_feed_num: Optional[int] = None
    show_comment_list: Optional[bool] = None
    show_mini_feed_list: Optional[bool] = None
    producer_fans_uid: Optional[str] = None
    producer_name: Optional[str] = None
    producer_avatar: Optional[str] = None
    producer_avatar_type: Optional[str] = None
    certification_name: Optional[str] = None
    certification_type: Optional[str] = None
    follow_status: Optional[str] = None
    produce_amount: Optional[int] = None
    raw_json: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JingtanSkuWikiDetailResponse(JingtanSkuWikiItem):
    raw_json: Optional[str] = None
    homepage_detail: Optional[JingtanSkuHomepageDetailItem] = None


@router.get("/sku-wikis", response_model=JingtanSkuWikiListResponse)
async def list_sku_wikis(
    search: Optional[str] = None,
    first_category: Optional[str] = None,
    second_category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    query = select(JingtanSkuWiki)
    count_query = select(func.count(JingtanSkuWiki.sku_id))

    if first_category:
        query = query.where(JingtanSkuWiki.first_category == first_category)
        count_query = count_query.where(JingtanSkuWiki.first_category == first_category)
    if second_category:
        query = query.where(JingtanSkuWiki.second_category == second_category)
        count_query = count_query.where(JingtanSkuWiki.second_category == second_category)
    if search:
        like = f"%{search}%"
        query = query.where(
            JingtanSkuWiki.sku_id.ilike(like)
            | JingtanSkuWiki.sku_name.ilike(like)
            | JingtanSkuWiki.author.ilike(like)
            | JingtanSkuWiki.owner.ilike(like)
        )
        count_query = count_query.where(
            JingtanSkuWiki.sku_id.ilike(like)
            | JingtanSkuWiki.sku_name.ilike(like)
            | JingtanSkuWiki.author.ilike(like)
            | JingtanSkuWiki.owner.ilike(like)
        )

    query = query.order_by(JingtanSkuWiki.sku_issue_time_ms.desc())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [JingtanSkuWikiItem.model_validate(x) for x in result.scalars().all()]
    return JingtanSkuWikiListResponse(total=total, items=items)


@router.get("/sku-wikis/{sku_id}", response_model=JingtanSkuWikiDetailResponse)
async def get_sku_wiki_detail(
    sku_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await db.execute(select(JingtanSkuWiki).where(JingtanSkuWiki.sku_id == sku_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="未找到该藏品")
    detail_result = await db.execute(select(JingtanSkuHomepageDetail).where(JingtanSkuHomepageDetail.sku_id == sku_id))
    homepage_detail = detail_result.scalar_one_or_none()
    return JingtanSkuWikiDetailResponse(
        **JingtanSkuWikiItem.model_validate(item).model_dump(),
        raw_json=item.raw_json,
        homepage_detail=(
            JingtanSkuHomepageDetailItem.model_validate(homepage_detail) if homepage_detail else None
        ),
    )
