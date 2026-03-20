import json
from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crawler.antfans_client import antfans_client
from app.database.models import JingtanSkuHomepageDetail, JingtanSkuWiki

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


def _as_bool(value) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True"):
        return True
    if value in (0, "0", "false", "False"):
        return False
    return None


async def crawl_jingtan_sku_homepage_details(
    db: AsyncSession,
    only_missing: bool = False,
    commit_every: int = 20,
    on_progress: Optional[Callable[[int, int, int, int], Awaitable[None]]] = None,
) -> Tuple[int, int, int]:
    op = settings.ANTFANS_OPERATION_TYPE_QUERY_SKU_HOMEPAGE
    rows = await db.execute(select(JingtanSkuWiki.sku_id).order_by(JingtanSkuWiki.sku_id.asc()))
    sku_ids = [row[0] for row in rows.all() if row[0]]
    if not sku_ids:
        logger.info("SKU 详情爬取结束: 无可处理 sku")
        return 0, 0, 0

    total = len(sku_ids)
    processed = 0
    upserted = 0
    failed = 0

    for sku_id in sku_ids:
        processed += 1
        if only_missing:
            existing = await db.get(JingtanSkuHomepageDetail, sku_id)
            if existing:
                if on_progress:
                    await on_progress(processed, upserted, failed, total)
                continue

        payload = [{"source": "collectionPreview", "targetSkuId": sku_id}]
        resp = await antfans_client.post_mgw_safe(operation_type=op, payload_obj=payload)
        data = resp.get("json")
        if resp.get("status") != 200 or not isinstance(data, dict):
            failed += 1
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue

        if data.get("bizStatusCode") != 10000:
            failed += 1
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue

        model = data.get("skuHomepageModel")
        if not isinstance(model, dict):
            failed += 1
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue

        collect_info = data.get("skuCollectionInfo") or {}
        producer = data.get("producerInfoModel") or {}
        now = datetime.utcnow()
        existing = await db.get(JingtanSkuHomepageDetail, sku_id)

        values = {
            "sku_name": _as_str(model.get("skuName")) or sku_id,
            "author": _as_str(model.get("author")),
            "owner": _as_str(model.get("owner")),
            "partner": _as_str(model.get("partner")),
            "partner_name": _as_str(model.get("partnerName")),
            "biz_type": _as_str(model.get("bizType")),
            "bg_conf": _as_str(model.get("bgConf")),
            "bg_info": _as_str(model.get("bgInfo")),
            "has_item": _as_bool(model.get("hasItem")),
            "mini_file_url": _as_str(model.get("miniFileUrl")),
            "origin_file_url": _as_str(model.get("originFileUrl")),
            "quantity_type": _as_str(model.get("quantityType")),
            "sku_desc": _as_str(model.get("skuDesc")),
            "sku_desc_image_file_ids": json.dumps(model.get("skuDescImageFileIds"), ensure_ascii=False),
            "sku_issue_time_ms": _as_int(model.get("skuIssueTime")),
            "sku_producer": _as_str(model.get("skuProducer")),
            "sku_quantity": _as_int(model.get("skuQuantity")),
            "sku_type": _as_str(model.get("skuType")),
            "collect_num": _as_int(collect_info.get("collectNum")),
            "user_collect_status": _as_bool(collect_info.get("userCollectStatus")),
            "comment_num": _as_int(data.get("commentNum")),
            "mini_feed_num": _as_int(data.get("miniFeedNum")),
            "show_comment_list": _as_bool(data.get("showCommentList")),
            "show_mini_feed_list": _as_bool(data.get("showMiniFeedList")),
            "producer_fans_uid": _as_str(producer.get("producerFansUid")),
            "producer_name": _as_str(producer.get("producerName")),
            "producer_avatar": _as_str(producer.get("producerAvatar")),
            "producer_avatar_type": _as_str(producer.get("producerAvatarType")),
            "certification_name": _as_str(producer.get("certificationName")),
            "certification_type": _as_str(producer.get("certificationType")),
            "follow_status": _as_str(producer.get("followStatus")),
            "produce_amount": _as_int(producer.get("produceAmount")),
            "raw_json": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            "updated_at": now,
        }

        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(
                JingtanSkuHomepageDetail(
                    sku_id=sku_id,
                    created_at=now,
                    **values,
                )
            )

        upserted += 1
        if processed % max(1, commit_every) == 0:
            await db.commit()
        if on_progress:
            await on_progress(processed, upserted, failed, total)

    await db.commit()
    logger.info(
        f"SKU 详情爬取完成: total={total} processed={processed} upserted={upserted} failed={failed}"
    )
    return processed, upserted, failed
