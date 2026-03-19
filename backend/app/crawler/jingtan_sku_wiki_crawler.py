import json
from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crawler.antfans_client import antfans_client
from app.database.models import JingtanSkuWiki

settings = get_settings()


def _as_int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _as_str(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


async def crawl_jingtan_sku_wiki(
    db: AsyncSession,
    start_page: int = 1,
    page_size: int = 20,
    max_pages: int = 5000,
    on_page_done: Optional[Callable[[int, int, int], Awaitable[None]]] = None,
) -> Tuple[int, int]:
    total_fetched = 0
    total_upserted = 0
    op = settings.ANTFANS_OPERATION_TYPE_QUERY_SKU_WIKI

    page = start_page
    while page <= max_pages:
        payload = [{"pageNum": page, "pageSize": page_size}]
        resp = await antfans_client.post_mgw_safe(operation_type=op, payload_obj=payload)
        if resp.get("status") != 200 or not isinstance(resp.get("json"), dict):
            logger.error(f"SKU wiki 请求失败: page={page} status={resp.get('status')}")
            break

        data = resp["json"]
        if data.get("bizStatusCode") != 10000:
            logger.error(f"SKU wiki bizStatusCode 异常: page={page} code={data.get('bizStatusCode')}")
            break

        records = data.get("skuWikiList") or []
        if not isinstance(records, list) or not records:
            break

        fetched = len(records)
        upserted = 0
        now = datetime.utcnow()

        for item in records:
            if not isinstance(item, dict):
                continue
            sku_id = _as_str(item.get("skuId"))
            sku_name = _as_str(item.get("skuName"))
            if not sku_id or not sku_name:
                continue

            result = await db.execute(select(JingtanSkuWiki).where(JingtanSkuWiki.sku_id == sku_id))
            existing = result.scalar_one_or_none()

            raw_json = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            if existing:
                existing.sku_name = sku_name
                existing.author = _as_str(item.get("author"))
                existing.owner = _as_str(item.get("owner"))
                existing.partner = _as_str(item.get("partner"))
                existing.partner_name = _as_str(item.get("partnerName"))
                existing.first_category = _as_str(item.get("firstCategory"))
                existing.first_category_name = _as_str(item.get("firstCategoryName"))
                existing.second_category = _as_str(item.get("secondCategory"))
                existing.second_category_name = _as_str(item.get("secondCategoryName"))
                existing.quantity_type = _as_str(item.get("quantityType"))
                existing.sku_quantity = _as_int(item.get("skuQuantity"))
                existing.sku_type = _as_str(item.get("skuType"))
                issue_ms = _as_int(item.get("skuIssueTime"))
                existing.sku_issue_time_ms = issue_ms
                existing.sku_producer = _as_str(item.get("skuProducer"))
                existing.mini_file_url = _as_str(item.get("miniFileUrl"))
                existing.raw_json = raw_json
                existing.updated_at = now
            else:
                issue_ms = _as_int(item.get("skuIssueTime"))
                db.add(
                    JingtanSkuWiki(
                        sku_id=sku_id,
                        sku_name=sku_name,
                        author=_as_str(item.get("author")),
                        owner=_as_str(item.get("owner")),
                        partner=_as_str(item.get("partner")),
                        partner_name=_as_str(item.get("partnerName")),
                        first_category=_as_str(item.get("firstCategory")),
                        first_category_name=_as_str(item.get("firstCategoryName")),
                        second_category=_as_str(item.get("secondCategory")),
                        second_category_name=_as_str(item.get("secondCategoryName")),
                        quantity_type=_as_str(item.get("quantityType")),
                        sku_quantity=_as_int(item.get("skuQuantity")),
                        sku_type=_as_str(item.get("skuType")),
                        sku_issue_time_ms=issue_ms,
                        sku_producer=_as_str(item.get("skuProducer")),
                        mini_file_url=_as_str(item.get("miniFileUrl")),
                        raw_json=raw_json,
                        created_at=now,
                        updated_at=now,
                    )
                )
            upserted += 1

        await db.commit()

        total_fetched += fetched
        total_upserted += upserted
        if on_page_done:
            await on_page_done(page, fetched, upserted)

        if fetched < page_size:
            break
        page += 1

    logger.info(f"SKU wiki 爬取完成: fetched={total_fetched} upserted={total_upserted}")
    return total_fetched, total_upserted
