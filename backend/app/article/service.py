"""文章生成与发布编排服务"""

import os
from datetime import datetime, timezone, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Article, ArticleImage
from app.article.llm import generate_article_content
from app.article.renderer import markdown_to_wechat_html
from app.article.reports import get_skill
from app.article.wechat_client import wechat_client

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
ARTICLES_DIR = os.path.join(STATIC_DIR, "articles")


def _article_dir(article_id: int) -> str:
    return os.path.join(ARTICLES_DIR, str(article_id))


# ---------- 生成文章 ----------

async def generate_article(
    db: AsyncSession,
    article_type: str,
    target_date: str | None = None,
) -> Article:
    """
    生成文章的完整流程：数据分析 → 图表生成 → AI 写作 → 存库
    article_type: daily / weekly / monthly
    """
    now = datetime.now(timezone.utc)
    skill = get_skill(article_type)

    # 1) 获取分析数据
    if article_type == "daily":
        kw = {"target_date": target_date or now.strftime("%Y-%m-%d")}
    elif article_type == "weekly":
        kw = {"end_date": target_date}
    elif article_type == "monthly":
        if target_date:
            y, m = int(target_date[:4]), int(target_date[5:7])
        else:
            y, m = now.year, now.month
        kw = {"year": y, "month": m}
    else:
        raise ValueError(f"未知文章类型: {article_type}")

    data = await skill.get_data(db, **kw)
    data_date = (
        data.get("date")
        or f"{data.get('start_date','')}"
           f"{'~' + data['end_date'] if data.get('end_date') else ''}"
        or data.get("month_label", "")
    )

    logger.info(f"文章数据分析完成: type={article_type}, data_date={data_date}")

    # 2) 先创建 article 记录以获取 ID
    article = Article(
        title="生成中...",
        article_type=article_type,
        data_date=data_date,
        status="generating",
    )
    db.add(article)
    await db.flush()

    output_dir = _article_dir(article.id)

    try:
        # 3) 生成图表
        charts = skill.generate_charts(data, output_dir)

        logger.info(f"图表生成完成: {list(charts.keys())}")

        # 保存图表记录
        for chart_key, chart_path in charts.items():
            img = ArticleImage(
                article_id=article.id,
                image_type=chart_key,
                file_path=chart_path,
            )
            db.add(img)

        # 4) AI 生成文章内容
        available_charts = [k for k in charts.keys() if k != "cover"]
        result = await generate_article_content(article_type, data, available_charts)

        # 5) 构建本地预览用的图表 URL 映射
        chart_urls = {}
        for key, path in charts.items():
            if key != "cover":
                # /static/articles/{id}/{filename}
                rel = os.path.relpath(path, STATIC_DIR).replace("\\", "/")
                chart_urls[key] = f"/static/{rel}"

        # 6) Markdown → HTML
        content_html = markdown_to_wechat_html(result["markdown"], chart_urls)

        # 7) 更新文章记录
        article.title = result["title"]
        article.content_markdown = result["markdown"]
        article.content_html = content_html
        article.summary = result["summary"]
        article.cover_image_url = charts.get("cover", "")
        article.status = "draft"
        article.analysis_data = str(data)  # 保留原始分析数据用于调试
        db.add(article)
        await db.commit()
        await db.refresh(article)

        logger.info(f"文章生成完成: id={article.id}, title={article.title}")
        return article

    except Exception as e:
        article.status = "failed"
        article.error_message = str(e)[:2000]
        db.add(article)
        await db.commit()
        await db.refresh(article)
        logger.error(f"文章生成失败: id={article.id}, error={e}")
        raise


# ---------- 发布到微信 ----------

async def publish_article(db: AsyncSession, article_id: int) -> Article:
    article = await db.get(Article, article_id)
    if not article:
        raise ValueError("文章不存在")
    if article.status not in ("draft", "failed"):
        raise ValueError(f"文章状态 {article.status} 不允许发布")

    if not wechat_client.is_configured:
        raise RuntimeError("微信公众号未配置 (WECHAT_APP_ID / WECHAT_APP_SECRET)")

    try:
        article.status = "publishing"
        db.add(article)
        await db.commit()

        # 1) 上传文章内图片到微信
        images = (await db.execute(
            select(ArticleImage).where(ArticleImage.article_id == article_id)
        )).scalars().all()

        wechat_chart_urls: dict[str, str] = {}
        cover_media_id = ""

        for img in images:
            if not img.file_path or not os.path.exists(img.file_path):
                continue
            if img.image_type == "cover":
                cover_media_id = await wechat_client.upload_material(img.file_path)
                img.wechat_media_url = cover_media_id
            else:
                url = await wechat_client.upload_image(img.file_path)
                wechat_chart_urls[img.image_type] = url
                img.wechat_media_url = url
            db.add(img)

        if not cover_media_id:
            raise RuntimeError("封面图上传失败")

        # 2) 用微信 URL 重新渲染 HTML
        wechat_html = markdown_to_wechat_html(
            article.content_markdown or "", wechat_chart_urls
        )

        # 3) 创建草稿
        media_id = await wechat_client.create_draft(
            title=article.title,
            content_html=wechat_html,
            cover_media_id=cover_media_id,
            digest=article.summary or "",
        )
        article.wechat_media_id = media_id

        # 4) 发布
        publish_id = await wechat_client.publish(media_id)
        article.wechat_publish_id = publish_id
        article.status = "published"
        article.published_at = datetime.now(timezone.utc)
        db.add(article)
        await db.commit()
        await db.refresh(article)

        logger.info(f"文章发布成功: id={article.id}, publish_id={publish_id}")
        return article

    except Exception as e:
        article.status = "failed"
        article.error_message = str(e)[:2000]
        db.add(article)
        await db.commit()
        await db.refresh(article)
        logger.error(f"文章发布失败: id={article.id}, error={e}")
        raise


# ---------- 查询 ----------

async def list_articles(
    db: AsyncSession,
    article_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Article], int]:
    query = select(Article)
    if article_type:
        query = query.where(Article.article_type == article_type)
    if status:
        query = query.where(Article.status == status)

    from sqlalchemy import func
    total = (await db.execute(
        select(func.count(Article.id)).where(
            *([Article.article_type == article_type] if article_type else []),
            *([Article.status == status] if status else []),
        )
    )).scalar() or 0

    query = query.order_by(desc(Article.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_article_detail(db: AsyncSession, article_id: int) -> dict[str, Any] | None:
    article = await db.get(Article, article_id)
    if not article:
        return None

    images = (await db.execute(
        select(ArticleImage).where(ArticleImage.article_id == article_id)
    )).scalars().all()

    return {
        "id": article.id,
        "title": article.title,
        "article_type": article.article_type,
        "data_date": article.data_date,
        "summary": article.summary,
        "content_html": article.content_html,
        "content_markdown": article.content_markdown,
        "cover_image_url": article.cover_image_url,
        "status": article.status,
        "wechat_media_id": article.wechat_media_id,
        "wechat_publish_id": article.wechat_publish_id,
        "published_at": str(article.published_at) if article.published_at else None,
        "error_message": article.error_message,
        "created_at": str(article.created_at),
        "updated_at": str(article.updated_at),
        "images": [
            {
                "id": img.id,
                "type": img.image_type,
                "file_path": img.file_path,
                "wechat_url": img.wechat_media_url,
            }
            for img in images
        ],
    }


async def delete_article(db: AsyncSession, article_id: int) -> bool:
    article = await db.get(Article, article_id)
    if not article:
        return False
    await db.delete(article)
    await db.commit()
    return True


async def update_article_content(
    db: AsyncSession,
    article_id: int,
    title: str | None = None,
    content_markdown: str | None = None,
    summary: str | None = None,
) -> Article | None:
    article = await db.get(Article, article_id)
    if not article:
        return None

    if title is not None:
        article.title = title
    if summary is not None:
        article.summary = summary
    if content_markdown is not None:
        article.content_markdown = content_markdown
        # 重新渲染 HTML
        images = (await db.execute(
            select(ArticleImage).where(ArticleImage.article_id == article_id)
        )).scalars().all()
        chart_urls = {}
        for img in images:
            if img.image_type != "cover" and img.file_path:
                rel = os.path.relpath(img.file_path, STATIC_DIR).replace("\\", "/")
                chart_urls[img.image_type] = f"/static/{rel}"
        article.content_html = markdown_to_wechat_html(content_markdown, chart_urls)

    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article

