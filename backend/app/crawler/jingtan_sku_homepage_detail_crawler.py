import asyncio
import json
import random
from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple

from loguru import logger
from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crawler.antfans_client import antfans_client
from app.database.models import JingtanSkuHomepageDetail, JingtanSkuWiki

settings = get_settings()
ALLOWED_FIRST_CATEGORIES = {
    "WH",
    "YL",
    "YS",
    "CW",
    "TY",
    "PP",
    "KJ",
    "ACG",
    "JQ",
    "AFY",
    "AYX",
    "AYCSJ",
    "QT",
}


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


def _throttle_delay(base: float) -> float:
    safe_base = max(0.8, float(base))
    return max(0.8, safe_base + safe_base * random.uniform(-0.2, 0.2))


def _extract_resp_error(resp: dict, data: Optional[dict]) -> str:
    status = resp.get("status")
    if not isinstance(data, dict):
        return f"HTTP={status}, 响应体非JSON对象"
    code = data.get("bizStatusCode")
    msg = _as_str(data.get("bizStatusMessage")) or ""
    return f"HTTP={status}, bizStatusCode={code}, bizStatusMessage={msg}"


async def _guess_wiki_categories(
    db: AsyncSession,
    author: Optional[str],
    owner: Optional[str],
    partner: Optional[str],
    partner_name: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    conditions = []
    if author:
        conditions.append(JingtanSkuWiki.author == author)
    if owner:
        conditions.append(JingtanSkuWiki.owner == owner)
    if partner:
        conditions.append(JingtanSkuWiki.partner == partner)
    if partner_name:
        conditions.append(JingtanSkuWiki.partner_name == partner_name)
    if not conditions:
        return None, None, None, None

    rows_result = await db.execute(
        select(
            JingtanSkuWiki.first_category,
            JingtanSkuWiki.first_category_name,
            JingtanSkuWiki.second_category,
            JingtanSkuWiki.second_category_name,
        )
        .where(JingtanSkuWiki.first_category.isnot(None))
        .where(or_(*conditions))
        .limit(500)
    )
    rows = rows_result.all()
    if not rows:
        return None, None, None, None

    first_counts: dict[str, int] = {}
    first_name_map: dict[str, str] = {}
    second_counts: dict[tuple[str, str], int] = {}
    second_name_map: dict[tuple[str, str], str] = {}
    for row in rows:
        first_category = _as_str(row[0])
        first_category_name = _as_str(row[1])
        second_category = _as_str(row[2])
        second_category_name = _as_str(row[3])
        if not first_category or first_category not in ALLOWED_FIRST_CATEGORIES:
            continue
        first_counts[first_category] = first_counts.get(first_category, 0) + 1
        if first_category_name and first_category not in first_name_map:
            first_name_map[first_category] = first_category_name
        if second_category:
            key = (first_category, second_category)
            second_counts[key] = second_counts.get(key, 0) + 1
            if second_category_name and key not in second_name_map:
                second_name_map[key] = second_category_name

    if not first_counts:
        return None, None, None, None
    best_first = max(first_counts.items(), key=lambda x: x[1])[0]
    best_first_name = first_name_map.get(best_first)

    second_candidates = [(k, v) for k, v in second_counts.items() if k[0] == best_first]
    if not second_candidates:
        return best_first, best_first_name, None, None
    best_second_key = max(second_candidates, key=lambda x: x[1])[0]
    return best_first, best_first_name, best_second_key[1], second_name_map.get(best_second_key)


async def _upsert_sku_homepage_detail(
    db: AsyncSession,
    sku_id: str,
    data: dict,
    now: datetime,
) -> bool:
    model = data.get("skuHomepageModel")
    if not isinstance(model, dict):
        return False

    collect_info = data.get("skuCollectionInfo") or {}
    producer = data.get("producerInfoModel") or {}
    detail_values = {
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

    detail_existing = await db.get(JingtanSkuHomepageDetail, sku_id)
    if detail_existing:
        for key, value in detail_values.items():
            setattr(detail_existing, key, value)
    else:
        db.add(
            JingtanSkuHomepageDetail(
                sku_id=sku_id,
                created_at=now,
                **detail_values,
            )
        )

    return True


async def _sync_sku_wiki_from_homepage(
    db: AsyncSession,
    sku_id: str,
    data: dict,
    now: datetime,
) -> bool:
    model = data.get("skuHomepageModel")
    if not isinstance(model, dict):
        return False

    model_first_category = _as_str(model.get("firstCategory"))
    model_first_category_name = _as_str(model.get("firstCategoryName"))
    model_second_category = _as_str(model.get("secondCategory"))
    model_second_category_name = _as_str(model.get("secondCategoryName"))
    if model_first_category not in ALLOWED_FIRST_CATEGORIES:
        model_first_category = None
        model_first_category_name = None
        model_second_category = None
        model_second_category_name = None
    if not model_first_category:
        guessed = await _guess_wiki_categories(
            db=db,
            author=_as_str(model.get("author")),
            owner=_as_str(model.get("owner")),
            partner=_as_str(model.get("partner")),
            partner_name=_as_str(model.get("partnerName")),
        )
        model_first_category, model_first_category_name, model_second_category, model_second_category_name = guessed

    wiki_values = {
        "sku_name": _as_str(model.get("skuName")) or sku_id,
        "author": _as_str(model.get("author")),
        "owner": _as_str(model.get("owner")),
        "partner": _as_str(model.get("partner")),
        "partner_name": _as_str(model.get("partnerName")),
        "quantity_type": _as_str(model.get("quantityType")),
        "sku_quantity": _as_int(model.get("skuQuantity")),
        "sku_type": _as_str(model.get("skuType")),
        "sku_issue_time_ms": _as_int(model.get("skuIssueTime")),
        "sku_producer": _as_str(model.get("skuProducer")),
        "mini_file_url": _as_str(model.get("miniFileUrl")),
        "raw_json": json.dumps(model, ensure_ascii=False, separators=(",", ":")),
        "updated_at": now,
    }
    wiki_existing = await db.get(JingtanSkuWiki, sku_id)
    if wiki_existing:
        for key, value in wiki_values.items():
            setattr(wiki_existing, key, value)
        if not wiki_existing.first_category and model_first_category:
            wiki_existing.first_category = model_first_category
        if not wiki_existing.first_category_name and model_first_category_name:
            wiki_existing.first_category_name = model_first_category_name
        if not wiki_existing.second_category and model_second_category:
            wiki_existing.second_category = model_second_category
        if not wiki_existing.second_category_name and model_second_category_name:
            wiki_existing.second_category_name = model_second_category_name
    else:
        db.add(
            JingtanSkuWiki(
                sku_id=sku_id,
                first_category=model_first_category,
                first_category_name=model_first_category_name,
                second_category=model_second_category,
                second_category_name=model_second_category_name,
                created_at=now,
                **wiki_values,
            )
        )
    return True


async def _upsert_sku_homepage_detail_and_try_sync_wiki(
    db: AsyncSession,
    sku_id: str,
    data: dict,
    now: datetime,
) -> bool:
    success = await _upsert_sku_homepage_detail(db=db, sku_id=sku_id, data=data, now=now)
    if not success:
        return False
    await db.flush()
    try:
        async with db.begin_nested():
            await _sync_sku_wiki_from_homepage(db=db, sku_id=sku_id, data=data, now=now)
            await db.flush()
    except Exception as e:
        logger.warning(f"sku_id={sku_id} wiki 同步失败，但详情已入库: {e}")
    return True


async def get_detail_numeric_sku_id_bounds(db: AsyncSession) -> Tuple[Optional[int], Optional[int]]:
    detail_bounds_result = await db.execute(
        select(
            func.max(cast(JingtanSkuHomepageDetail.sku_id, Integer)),
            func.min(cast(JingtanSkuHomepageDetail.sku_id, Integer)),
        ).where(JingtanSkuHomepageDetail.sku_id.op("~")("^[0-9]+$"))
    )
    detail_max, detail_min = detail_bounds_result.one()
    max_sku_id = _as_int(detail_max)
    min_sku_id = _as_int(detail_min)
    if max_sku_id is None or min_sku_id is None:
        return None, None
    return max_sku_id, min_sku_id


async def _sku_homepage_detail_exists(db: AsyncSession, sku_id: str) -> bool:
    existing = await db.get(JingtanSkuHomepageDetail, sku_id)
    return existing is not None


async def crawl_jingtan_sku_homepage_details(
    db: AsyncSession,
    only_missing: bool = True,
    commit_every: int = 20,
    on_progress: Optional[Callable[[int, int, int, int], Awaitable[None]]] = None,
    on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> Tuple[int, int, int]:
    op = settings.ANTFANS_OPERATION_TYPE_QUERY_SKU_HOMEPAGE
    if only_missing:
        # 一条 SQL 取出 wiki 中详情表里缺失的 sku_id，避免逐条主键查询
        rows = await db.execute(
            select(JingtanSkuWiki.sku_id)
            .where(
                ~JingtanSkuWiki.sku_id.in_(
                    select(JingtanSkuHomepageDetail.sku_id)
                )
            )
            .order_by(JingtanSkuWiki.sku_id.asc())
        )
    else:
        rows = await db.execute(select(JingtanSkuWiki.sku_id).order_by(JingtanSkuWiki.sku_id.asc()))
    sku_ids = [row[0] for row in rows.all() if row[0]]
    if not sku_ids:
        logger.info("SKU 详情爬取结束: 无缺失 sku")
        return 0, 0, 0

    total = len(sku_ids)
    processed = 0
    upserted = 0
    failed = 0

    for sku_id in sku_ids:
        processed += 1
        payload = [{"source": "collectionPreview", "targetSkuId": sku_id}]
        try:
            resp = await antfans_client.post_mgw_safe(operation_type=op, payload_obj=payload)
        except Exception as e:
            failed += 1
            err_msg = f"sku_id={sku_id} 请求异常: {e}"
            logger.warning(err_msg)
            if on_error:
                await on_error(sku_id, str(e))
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue
        data = resp.get("json")
        if resp.get("status") != 200 or not isinstance(data, dict):
            failed += 1
            err_msg = _extract_resp_error(resp, data if isinstance(data, dict) else None)
            logger.warning(f"sku_id={sku_id} 请求失败: {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue

        if data.get("bizStatusCode") != 10000:
            failed += 1
            err_msg = _extract_resp_error(resp, data)
            logger.warning(f"sku_id={sku_id} 业务失败: {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue

        if not isinstance(data.get("skuHomepageModel"), dict):
            failed += 1
            err_msg = "skuHomepageModel 缺失或类型异常"
            logger.warning(f"sku_id={sku_id} 数据失败: {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue

        now = datetime.utcnow()
        try:
            success = await _upsert_sku_homepage_detail_and_try_sync_wiki(
                db=db,
                sku_id=sku_id,
                data=data,
                now=now,
            )
        except Exception as e:
            failed += 1
            err_msg = f"入库异常: {e}"
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(processed, upserted, failed, total)
            continue
        if success:
            upserted += 1
        else:
            failed += 1
            err_msg = "入库失败: 详情结构不完整"
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
        if processed % max(1, commit_every) == 0:
            await db.commit()
        if on_progress:
            await on_progress(processed, upserted, failed, total)

    await db.commit()
    logger.info(
        f"SKU 详情爬取完成: total={total} processed={processed} upserted={upserted} failed={failed}"
    )
    return processed, upserted, failed


async def crawl_jingtan_sku_homepage_details_desc_backfill(
    db: AsyncSession,
    start_sku_id: Optional[int] = None,
    stop_sku_id: Optional[int] = None,
    max_scan: Optional[int] = None,
    commit_every: int = 20,
    request_interval_seconds: Optional[float] = None,
    on_progress: Optional[Callable[[int, int, int, int, int], Awaitable[None]]] = None,
    on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> Tuple[int, int, int, int, list[str], list[str]]:
    op = settings.ANTFANS_OPERATION_TYPE_QUERY_SKU_HOMEPAGE
    db_max_sku_id, db_min_sku_id = await get_detail_numeric_sku_id_bounds(db)
    start = start_sku_id if start_sku_id is not None else db_max_sku_id
    if start is None:
        raise ValueError("数据库中无可用起始 sku_id")
    if stop_sku_id is not None:
        lower_bound = max(0, int(stop_sku_id))
    elif db_min_sku_id is not None:
        lower_bound = max(0, int(db_min_sku_id))
    else:
        raise ValueError("数据库中无可用最小 sku_id")

    scanned = 0
    inserted = 0
    skipped = 0
    failed = 0
    skipped_sku_ids: list[str] = []
    failed_sku_ids: list[str] = []
    current = int(start)
    max_scan_limit = int(max_scan) if max_scan is not None else None
    base_interval = (
        float(request_interval_seconds)
        if request_interval_seconds is not None
        else max(1.2, float(settings.ANTFANS_REQUEST_DELAY or 0))
    )

    while current >= lower_bound and (max_scan_limit is None or scanned < max(1, max_scan_limit)):
        sku_id = str(current)
        scanned += 1
        if await _sku_homepage_detail_exists(db, sku_id):
            skipped += 1
            skipped_sku_ids.append(sku_id)
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, current)
            current -= 1
            continue

        payload = [{"source": "collectionPreview", "targetSkuId": sku_id}]
        try:
            resp = await antfans_client.post_mgw_safe(operation_type=op, payload_obj=payload)
        except Exception as e:
            failed += 1
            err_msg = f"请求异常: {e}"
            failed_sku_ids.append(sku_id)
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, current)
            current -= 1
            continue
        await asyncio.sleep(_throttle_delay(base_interval))
        data = resp.get("json")
        if resp.get("status") != 200 or not isinstance(data, dict) or data.get("bizStatusCode") != 10000:
            failed += 1
            err_msg = _extract_resp_error(resp, data if isinstance(data, dict) else None)
            failed_sku_ids.append(sku_id)
            logger.warning(f"sku_id={sku_id} 回填失败: {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, current)
            current -= 1
            continue

        now = datetime.utcnow()
        try:
            success = await _upsert_sku_homepage_detail_and_try_sync_wiki(
                db=db,
                sku_id=sku_id,
                data=data,
                now=now,
            )
        except Exception as e:
            failed += 1
            err_msg = f"入库异常: {e}"
            failed_sku_ids.append(sku_id)
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, current)
            current -= 1
            continue
        if success:
            inserted += 1
        else:
            failed += 1
            err_msg = "入库失败: 详情结构不完整"
            failed_sku_ids.append(sku_id)
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)

        if scanned % max(1, commit_every) == 0:
            await db.commit()
        if on_progress:
            await on_progress(scanned, inserted, skipped, failed, current)
        current -= 1

    await db.commit()
    logger.info(
        f"SKU 倒序回填完成: start={start} scanned={scanned} inserted={inserted} skipped={skipped} failed={failed}"
    )
    logger.info(f"skipped_sku_ids: {json.dumps(skipped_sku_ids, ensure_ascii=False)}")
    logger.info(f"failed_sku_ids: {json.dumps(failed_sku_ids, ensure_ascii=False)}")
    return scanned, inserted, skipped, failed, skipped_sku_ids, failed_sku_ids


async def crawl_jingtan_sku_details_from_id_list(
    db: AsyncSession,
    sku_ids: list[str],
    commit_every: int = 20,
    request_interval_seconds: Optional[float] = None,
    on_progress: Optional[Callable[[int, int, int, int, int], Awaitable[None]]] = None,
    on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> Tuple[int, int, int, int]:
    """从指定的 sku_id 列表中，仅补齐详情表中不存在的记录。

    Returns:
        (total, inserted, skipped, failed)
    """
    op = settings.ANTFANS_OPERATION_TYPE_QUERY_SKU_HOMEPAGE
    base_interval = (
        float(request_interval_seconds)
        if request_interval_seconds is not None
        else max(1.2, float(settings.ANTFANS_REQUEST_DELAY or 0))
    )

    total = len(sku_ids)
    scanned = 0
    inserted = 0
    skipped = 0
    failed = 0

    for sku_id in sku_ids:
        scanned += 1

        if await _sku_homepage_detail_exists(db, sku_id):
            skipped += 1
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, total)
            continue

        payload = [{"source": "collectionPreview", "targetSkuId": sku_id}]
        try:
            resp = await antfans_client.post_mgw_safe(operation_type=op, payload_obj=payload)
        except Exception as e:
            failed += 1
            err_msg = f"请求异常: {e}"
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, str(e))
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, total)
            continue

        await asyncio.sleep(_throttle_delay(base_interval))
        data = resp.get("json")
        if resp.get("status") != 200 or not isinstance(data, dict) or data.get("bizStatusCode") != 10000:
            failed += 1
            err_msg = _extract_resp_error(resp, data if isinstance(data, dict) else None)
            logger.warning(f"sku_id={sku_id} 请求失败: {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, total)
            continue

        if not isinstance(data.get("skuHomepageModel"), dict):
            failed += 1
            err_msg = "skuHomepageModel 缺失或类型异常"
            logger.warning(f"sku_id={sku_id} 数据失败: {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, total)
            continue

        now = datetime.utcnow()
        try:
            success = await _upsert_sku_homepage_detail_and_try_sync_wiki(
                db=db,
                sku_id=sku_id,
                data=data,
                now=now,
            )
        except Exception as e:
            failed += 1
            err_msg = f"入库异常: {e}"
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)
            if on_progress:
                await on_progress(scanned, inserted, skipped, failed, total)
            continue

        if success:
            inserted += 1
        else:
            failed += 1
            err_msg = "入库失败: 详情结构不完整"
            logger.warning(f"sku_id={sku_id} {err_msg}")
            if on_error:
                await on_error(sku_id, err_msg)

        if scanned % max(1, commit_every) == 0:
            await db.commit()
        if on_progress:
            await on_progress(scanned, inserted, skipped, failed, total)

    await db.commit()
    logger.info(
        f"SKU ID列表补齐完成: total={total} inserted={inserted} skipped={skipped} failed={failed}"
    )
    return total, inserted, skipped, failed


async def crawl_jingtan_sku_details_around_max_id(
    db: AsyncSession,
    spread_backward: int = 200,
    spread_forward: int = 100,
    commit_every: int = 20,
    request_interval_seconds: Optional[float] = None,
    on_progress: Optional[Callable[[int, int, int, int, int], Awaitable[None]]] = None,
    on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> Tuple[int, int, int, int]:
    """围绕当前最大 sku_id，向前（历史）spread_backward 个、向后（新增）spread_forward 个，补齐缺失的详情记录。

    Returns:
        (total, inserted, skipped, failed)
    """
    max_sku_id, _ = await get_detail_numeric_sku_id_bounds(db)
    if max_sku_id is None:
        logger.info("SKU 详情表无记录，跳过邻域补齐")
        return 0, 0, 0, 0

    lower = max(1, max_sku_id - spread_backward)
    upper = max_sku_id + spread_forward
    sku_ids = [str(i) for i in range(lower, upper + 1)]
    logger.info(f"SKU 邻域补齐: max_sku_id={max_sku_id} 范围 [{lower}, {upper}] 共 {len(sku_ids)} 个")

    return await crawl_jingtan_sku_details_from_id_list(
        db,
        sku_ids=sku_ids,
        commit_every=commit_every,
        request_interval_seconds=request_interval_seconds,
        on_progress=on_progress,
        on_error=on_error,
    )
