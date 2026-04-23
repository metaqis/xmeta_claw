"""文章管理 API"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import get_db
from app.api.auth import get_current_user
from app.article.service import (
    generate_article,
    send_to_wechat,
    list_articles,
    get_article_detail,
    delete_article,
    update_article_content,
)

router = APIRouter(prefix="/articles", tags=["文章管理"])


# ---------- 请求/响应模型 ----------

class GenerateRequest(BaseModel):
    article_type: str  # daily / weekly / monthly
    target_date: str | None = None  # YYYY-MM-DD


class UpdateRequest(BaseModel):
    title: str | None = None
    content_markdown: str | None = None
    summary: str | None = None


class ArticleItem(BaseModel):
    id: int
    title: str
    article_type: str
    data_date: str | None = None
    summary: str | None = None
    status: str
    cover_image_url: str | None = None
    created_at: str | None = None


class ArticleListResponse(BaseModel):
    items: list[ArticleItem]
    total: int
    page: int
    page_size: int


# ---------- 接口 ----------

@router.get("/", response_model=ArticleListResponse)
async def api_list_articles(
    article_type: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    articles, total = await list_articles(db, article_type, status, page, page_size)
    return ArticleListResponse(
        items=[
            ArticleItem(
                id=a.id,
                title=a.title,
                article_type=a.article_type,
                data_date=a.data_date,
                summary=a.summary,
                status=a.status,
                cover_image_url=a.cover_image_url,
                created_at=str(a.created_at) if a.created_at else None,
            )
            for a in articles
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{article_id}")
async def api_get_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    detail = await get_article_detail(db, article_id)
    if not detail:
        raise HTTPException(404, "文章不存在")
    return detail


@router.post("/generate")
async def api_generate_article(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    if req.article_type not in ("daily", "weekly", "monthly"):
        raise HTTPException(400, "article_type 必须为 daily/weekly/monthly")
    try:
        article = await generate_article(db, req.article_type, req.target_date)
        return {
            "id": article.id,
            "title": article.title,
            "status": article.status,
            "message": "文章生成成功",
        }
    except Exception as e:
        raise HTTPException(500, f"文章生成失败: {e}")


@router.post("/{article_id}/send_to_wechat")
async def api_send_to_wechat(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    try:
        article = await send_to_wechat(db, article_id)
        return {
            "id": article.id,
            "status": article.status,
            "wechat_media_id": article.wechat_media_id,
            "message": "草稿已创建，请在微信公众平台发布",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.put("/{article_id}")
async def api_update_article(
    article_id: int,
    req: UpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    article = await update_article_content(
        db, article_id,
        title=req.title,
        content_markdown=req.content_markdown,
        summary=req.summary,
    )
    if not article:
        raise HTTPException(404, "文章不存在")
    return {"id": article.id, "title": article.title, "status": article.status}


@router.delete("/{article_id}")
async def api_delete_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    ok = await delete_article(db, article_id)
    if not ok:
        raise HTTPException(404, "文章不存在")
    return {"message": "已删除"}
