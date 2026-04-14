"""Tool 执行器：名称 → 执行函数映射"""
import json
import re
from datetime import date as date_type, datetime, timezone, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crawler.client import crawler_client
from app.database.models import (
    Archive, IP, LaunchCalendar, LaunchDetail, Platform, Plane,
    JingtanSkuWiki, JingtanSkuHomepageDetail,
    MarketDailySummary, MarketPlaneSnapshot, MarketIPSnapshot,
    MarketArchiveSnapshot, MarketPlaneCensus, MarketTopCensus,
)
from app.core.cache import cache_get, cache_set, make_cache_key

XMETA_BASE = "https://xmeta.x-metash.cn/prod/xmeta_mall/#/pages"


def _archive_link(archive_id, platform_id=741) -> str:
    return f"{XMETA_BASE}/salesDetail/index?archiveId={archive_id}&platformId={platform_id or 741}&active=6"


def _ip_link(source_uid, from_type=1) -> str | None:
    if source_uid is None:
        return None
    return f"{XMETA_BASE}/ltwd/index?uid={source_uid}&fromType={from_type or 1}"


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value)).strip().lower()


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _archive_match_meta(
    archive_name: str | None,
    ip_name: str | None,
    archive_id: str | None,
    keyword: str,
) -> tuple[int, str]:
    normalized_keyword = _normalize_text(keyword)
    normalized_name = _normalize_text(archive_name)
    normalized_ip = _normalize_text(ip_name)
    normalized_archive_id = _normalize_text(archive_id)

    if not normalized_keyword:
        return 99, "none"
    if normalized_archive_id == normalized_keyword:
        return 0, "archive_id_exact"
    if normalized_name == normalized_keyword:
        return 1, "archive_name_exact"
    if normalized_ip == normalized_keyword:
        return 2, "ip_name_exact"
    if normalized_name.startswith(normalized_keyword):
        return 3, "archive_name_prefix"
    if normalized_ip.startswith(normalized_keyword):
        return 4, "ip_name_prefix"
    if normalized_keyword in normalized_name:
        return 5, "archive_name_contains"
    if normalized_keyword in normalized_ip:
        return 6, "ip_name_contains"
    if normalized_keyword in normalized_archive_id:
        return 7, "archive_id_contains"
    return 99, "none"


def _ip_match_meta(ip_name: str | None, keyword: str, source_uid: Any = None) -> tuple[int, str]:
    normalized_keyword = _normalize_text(keyword)
    normalized_name = _normalize_text(ip_name)
    normalized_uid = _normalize_text(source_uid)

    if not normalized_keyword:
        return 99, "none"
    if normalized_name == normalized_keyword:
        return 0, "ip_name_exact"
    if normalized_uid == normalized_keyword:
        return 1, "source_uid_exact"
    if normalized_name.startswith(normalized_keyword):
        return 2, "ip_name_prefix"
    if normalized_keyword in normalized_name:
        return 3, "ip_name_contains"
    if normalized_keyword in normalized_uid:
        return 4, "source_uid_contains"
    return 99, "none"


def _humanize_match_type(match_type: str | None) -> str:
    mapping = {
        "archive_id_exact": "ID精确匹配",
        "archive_name_exact": "藏品名精确匹配",
        "ip_name_exact": "IP名精确匹配",
        "archive_name_prefix": "藏品名前缀匹配",
        "ip_name_prefix": "IP名前缀匹配",
        "archive_name_contains": "藏品名模糊匹配",
        "ip_name_contains": "IP名模糊匹配",
        "archive_id_contains": "ID模糊匹配",
        "source_uid_exact": "来源ID精确匹配",
        "source_uid_contains": "来源ID模糊匹配",
    }
    return mapping.get(match_type or "", "模糊匹配")


def _source_label(source: str | None) -> str:
    return "数据库" if source == "db" else "在线"


def _build_recommendation_item(entity_type: str, entity_id: Any, name: str | None, match_type: str | None, source: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    item = {
        "entity_type": entity_type,
        "id": entity_id,
        "name": name,
        "match_type": match_type,
        "match_label": _humanize_match_type(match_type),
        "source": source,
        "source_label": _source_label(source),
        "selection_label": f"{name}（{_source_label(source)}，{_humanize_match_type(match_type)}）" if name else None,
    }
    if extra:
        item.update(extra)
    return item


def _to_public_recommendation(item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "name": item.get("name"),
        "entity_type": item.get("entity_type"),
        "platform": item.get("platform"),
        "ip": item.get("ip"),
    }


def _to_public_archive_item(item: dict[str, Any], index: int | None = None) -> dict[str, Any]:
    public_item = {
        "name": item.get("name"),
        "type": item.get("type"),
        "platform": item.get("platform"),
        "ip": item.get("ip"),
        "issue_time": item.get("issue_time"),
        "link": item.get("link"),
    }
    if index is not None:
        public_item["index"] = index
    return public_item


def _to_public_ip_item(item: dict[str, Any], index: int | None = None) -> dict[str, Any]:
    public_item = {
        "name": item.get("name"),
        "platform": item.get("platform"),
        "fans_count": item.get("fans_count"),
        "archive_count": item.get("archive_count"),
        "link": item.get("link"),
    }
    if index is not None:
        public_item["index"] = index
    return public_item


async def _fetch_online_archive_candidates(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    payload = {
        "timeType": 0,
        "pageNum": 1,
        "pageSize": min(20, max(limit, 5)),
        "dealCountSortType": False,
        "platformIdList": [],
        "communityIpIdList": [],
        "searchName": keyword,
        "topCode": "",
    }
    resp = await crawler_client.post_safe("/h5/market/marketArchivePage", payload)
    if not resp or resp.get("code") != 200:
        return []

    data = resp.get("data", {})
    records = data.get("records", [])
    items: list[dict[str, Any]] = []
    for record in records[:limit]:
        score, match_type = _archive_match_meta(
            record.get("archiveName"),
            record.get("ipName") or record.get("communityIpName"),
            record.get("archiveId"),
            keyword,
        )
        items.append({
            "archive_id": str(record.get("archiveId") or ""),
            "name": record.get("archiveName"),
            "ip": record.get("ipName") or record.get("communityIpName"),
            "platform": record.get("platformName") or "鲸探",
            "match_type": match_type,
            "match_label": _humanize_match_type(match_type),
            "match_score": score,
            "deal_count": record.get("dealCount"),
            "avg_amount": record.get("avgAmount"),
            "source": "online",
            "source_label": _source_label("online"),
            "link": _archive_link(record.get("archiveId"), record.get("platformId", 741)),
        })
    return items


async def _fetch_online_ip_candidates(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    payload = {
        "timeType": 0,
        "pageNum": 1,
        "pageSize": min(20, max(limit, 5)),
        "platformIdList": [],
        "communityIpIdList": [],
        "searchName": keyword,
    }
    resp = await crawler_client.post_safe("/h5/market/ipPage", payload)
    if not resp or resp.get("code") != 200:
        return []

    data = resp.get("data", {})
    records = data.get("records", [])
    items: list[dict[str, Any]] = []
    for record in records[:limit]:
        score, match_type = _ip_match_meta(record.get("name"), keyword, record.get("communityIpId"))
        community_ip_id = record.get("communityIpId")
        items.append({
            "source_uid": community_ip_id,
            "name": record.get("name"),
            "archive_count": record.get("archiveCount"),
            "market_amount": record.get("marketAmount"),
            "hot": record.get("hot"),
            "match_type": match_type,
            "match_label": _humanize_match_type(match_type),
            "match_score": score,
            "source": "online",
            "source_label": _source_label("online"),
            "link": _ip_link(community_ip_id, record.get("fromType", 1)),
        })
    return items


# ── DB 工具 ──────────────────────────────────────────────────

async def _search_archives(db: AsyncSession, **kwargs) -> str:
    keyword = str(kwargs.get("keyword", "") or "").strip()
    platform_id = kwargs.get("platform_id")
    page = max(1, kwargs.get("page", 1))
    page_size = min(50, kwargs.get("page_size", 20))

    stmt = select(Archive).options(selectinload(Archive.platform), selectinload(Archive.ip))
    if keyword:
        normalized_keyword = keyword.lower()
        stmt = stmt.outerjoin(IP).where(
            or_(
                Archive.archive_name.ilike(f"%{keyword}%"),
                Archive.archive_id.ilike(f"%{keyword}%"),
                IP.ip_name.ilike(f"%{keyword}%"),
            )
        ).order_by(
            case(
                (func.lower(Archive.archive_id) == normalized_keyword, 0),
                (func.lower(Archive.archive_name) == normalized_keyword, 1),
                (func.lower(IP.ip_name) == normalized_keyword, 2),
                (Archive.archive_name.ilike(f"{keyword}%"), 3),
                (Archive.archive_id.ilike(f"{keyword}%"), 4),
                (IP.ip_name.ilike(f"{keyword}%"), 5),
                else_=6,
            ),
            Archive.issue_time.desc().nullslast(),
            Archive.archive_id.desc(),
        )
    else:
        stmt = stmt.order_by(Archive.archive_id.desc())

    if platform_id:
        stmt = stmt.where(Archive.platform_id == platform_id)

    # 简化 COUNT 查询：独立构建，不套用带 ORDER BY / selectinload 的主查询
    count_filter = []
    if keyword:
        count_filter.append(
            or_(
                Archive.archive_name.ilike(f"%{keyword}%"),
                Archive.archive_id.ilike(f"%{keyword}%"),
            )
        )
    if platform_id:
        count_filter.append(Archive.platform_id == platform_id)
    if count_filter:
        count_stmt = select(func.count()).select_from(Archive).where(*count_filter)
    else:
        count_stmt = select(func.count()).select_from(Archive)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    archives = result.unique().scalars().all()

    items = []
    for archive in archives:
        score, match_type = _archive_match_meta(
            archive.archive_name,
            archive.ip.ip_name if archive.ip else None,
            archive.archive_id,
            keyword,
        )
        items.append({
            "archive_id": archive.archive_id,
            "name": archive.archive_name,
            "type": archive.archive_type,
            "total_count": archive.total_goods_count,
            "platform": archive.platform.name if archive.platform else None,
            "ip": archive.ip.ip_name if archive.ip else None,
            "issue_time": archive.issue_time.strftime("%Y-%m-%d") if archive.issue_time else None,
            "match_type": match_type if keyword else None,
            "match_label": _humanize_match_type(match_type) if keyword else None,
            "match_score": score if keyword else None,
            "source": "db",
            "source_label": _source_label("db"),
            "link": _archive_link(archive.archive_id, archive.platform_id),
        })
    public_items = [_to_public_archive_item(item, index + 1) for index, item in enumerate(items[:5])]
    return json.dumps({
        "total": total,
        "page": page,
        "items": items,
        "public_items": public_items,
        "recommended_reply_format": {
            "style": "numbered_list",
            "instruction": "若用户还未明确具体对象，优先使用 public_items 按编号展示候选并让用户选择，不要暴露任何ID。",
        } if keyword and len(items) > 1 else None,
    }, ensure_ascii=False)


async def _resolve_entities(db: AsyncSession, **kwargs) -> str:
    keyword = str(kwargs.get("keyword", "") or "").strip()
    limit = min(10, max(1, int(kwargs.get("limit", 5))))

    if not keyword:
        return json.dumps({"error": "keyword 不能为空"}, ensure_ascii=False)

    archive_stmt = (
        select(Archive)
        .options(selectinload(Archive.platform), selectinload(Archive.ip))
        .outerjoin(IP)
        .where(
            or_(
                Archive.archive_name.ilike(f"%{keyword}%"),
                Archive.archive_id.ilike(f"%{keyword}%"),
                IP.ip_name.ilike(f"%{keyword}%"),
            )
        )
        .limit(30)
    )
    archive_result = await db.execute(archive_stmt)
    archive_candidates = archive_result.unique().scalars().all()

    # 排序时缓存 match_meta 结果，避免重复计算
    archive_scored: list[tuple[Any, int, str]] = []
    for archive in archive_candidates:
        score, match_type = _archive_match_meta(
            archive.archive_name,
            archive.ip.ip_name if archive.ip else None,
            archive.archive_id,
            keyword,
        )
        archive_scored.append((archive, score, match_type))
    archive_scored.sort(
        key=lambda item: (
            item[1],
            -(item[0].issue_time.timestamp()) if item[0].issue_time else float("inf"),
            str(item[0].archive_id),
        ),
    )

    archives = []
    for archive, score, match_type in archive_scored[:limit]:
        archives.append({
            "archive_id": archive.archive_id,
            "name": archive.archive_name,
            "ip": archive.ip.ip_name if archive.ip else None,
            "platform": archive.platform.name if archive.platform else None,
            "issue_time": archive.issue_time.strftime("%Y-%m-%d %H:%M") if archive.issue_time else None,
            "match_type": match_type,
            "match_label": _humanize_match_type(match_type),
            "match_score": score,
            "source": "db",
            "source_label": _source_label("db"),
            "link": _archive_link(archive.archive_id, archive.platform_id),
        })

    ip_stmt = (
        select(IP)
        .options(selectinload(IP.platform))
        .where(IP.ip_name.ilike(f"%{keyword}%"))
        .limit(30)
    )
    ip_result = await db.execute(ip_stmt)
    ip_candidates = ip_result.unique().scalars().all()

    # 排序时缓存 match_meta 结果，避免重复计算
    ip_scored: list[tuple[Any, int, str]] = []
    for ip in ip_candidates:
        score, match_type = _ip_match_meta(ip.ip_name, keyword, ip.source_uid)
        ip_scored.append((ip, score, match_type))
    ip_scored.sort(
        key=lambda item: (
            item[1],
            -(item[0].fans_count or 0),
            item[0].id,
        ),
    )

    ips = []
    for ip, score, match_type in ip_scored[:limit]:
        ips.append({
            "id": ip.id,
            "name": ip.ip_name,
            "platform": ip.platform.name if ip.platform else None,
            "fans_count": ip.fans_count,
            "match_type": match_type,
            "match_label": _humanize_match_type(match_type),
            "match_score": score,
            "source": "db",
            "source_label": _source_label("db"),
            "link": _ip_link(ip.source_uid, ip.from_type),
        })

    best_match = None
    archive_top = archives[0] if archives else None
    ip_top = ips[0] if ips else None
    if archive_top and archive_top["match_score"] <= 1:
        best_match = {
            "entity_type": "archive",
            "archive_id": archive_top["archive_id"],
            "name": archive_top["name"],
            "match_type": archive_top["match_type"],
        }
    elif ip_top and ip_top["match_score"] <= 0:
        best_match = {
            "entity_type": "ip",
            "ip_id": ip_top["id"],
            "name": ip_top["name"],
            "match_type": ip_top["match_type"],
        }

    online_archives: list[dict[str, Any]] = []
    online_ips: list[dict[str, Any]] = []
    if best_match is None or (not archives and not ips):
        online_archives = await _fetch_online_archive_candidates(keyword, limit)
        online_ips = await _fetch_online_ip_candidates(keyword, limit)

        if best_match is None:
            online_archive_top = online_archives[0] if online_archives else None
            online_ip_top = online_ips[0] if online_ips else None
            if online_archive_top and online_archive_top["match_score"] <= 1:
                best_match = {
                    "entity_type": "online_archive",
                    "archive_id": online_archive_top["archive_id"],
                    "name": online_archive_top["name"],
                    "match_type": online_archive_top["match_type"],
                }
            elif online_ip_top and online_ip_top["match_score"] <= 0:
                best_match = {
                    "entity_type": "online_ip",
                    "source_uid": online_ip_top["source_uid"],
                    "name": online_ip_top["name"],
                    "match_type": online_ip_top["match_type"],
                }

    recommendations: list[dict[str, Any]] = []
    for archive in archives[:3]:
        recommendations.append(_build_recommendation_item(
            "archive",
            archive["archive_id"],
            archive["name"],
            archive.get("match_type"),
            "db",
            {"ip": archive.get("ip"), "platform": archive.get("platform")},
        ))
    for ip in ips[:3]:
        recommendations.append(_build_recommendation_item(
            "ip",
            ip["id"],
            ip["name"],
            ip.get("match_type"),
            "db",
            {"platform": ip.get("platform")},
        ))
    if not recommendations:
        for archive in online_archives[:3]:
            recommendations.append(_build_recommendation_item(
                "online_archive",
                archive["archive_id"],
                archive["name"],
                archive.get("match_type"),
                "online",
                {"ip": archive.get("ip"), "platform": archive.get("platform")},
            ))
        for ip in online_ips[:3]:
            recommendations.append(_build_recommendation_item(
                "online_ip",
                ip["source_uid"],
                ip["name"],
                ip.get("match_type"),
                "online",
                {},
            ))

    if best_match is None and len(recommendations) == 1:
        candidate = recommendations[0]
        best_match = {
            "entity_type": candidate["entity_type"],
            "name": candidate["name"],
            "match_type": candidate["match_type"],
            "id": candidate["id"],
        }

    clarification_question = None
    if best_match is None and recommendations:
        clarification_question = "我找到了几个可能的对象，请回复序号或名称确认你想查的是哪一个。"

    recommended_reply_format = None
    if best_match is None and recommendations:
        recommended_reply_format = {
            "style": "numbered_list",
            "instruction": "按 1、2、3 编号列出候选，每项只显示名称和平台信息；结尾请用户回复序号或名称确认。不要展示匹配方式、来源等内部信息。",
        }

    public_recommendations = [
        _to_public_recommendation(item, index + 1)
        for index, item in enumerate(recommendations[:5])
    ]

    return json.dumps({
        "keyword": keyword,
        "best_match": best_match,
        "needs_clarification": best_match is None and (len(recommendations) > 1),
        "archives": archives,
        "ips": ips,
        "online_archives": online_archives,
        "online_ips": online_ips,
        "recommendations": recommendations[:5],
        "public_recommendations": public_recommendations,
        "clarification_question": clarification_question,
        "recommended_reply_format": recommended_reply_format,
        "note": "面向用户回复时，只使用 public_recommendations 中的名称和编号组织候选列表。严禁在回复中出现 archive_id、ip_id、source_uid、match_type、match_score、source 等内部字段，也不要提及'精确匹配'、'模糊匹配'、'来源数据库'等元信息。",
    }, ensure_ascii=False)


async def _get_archive_detail(db: AsyncSession, **kwargs) -> str:
    archive_id = str(kwargs.get("archive_id", "") or "").strip()
    stmt = select(Archive).options(
        selectinload(Archive.platform), selectinload(Archive.ip)
    ).where(Archive.archive_id == archive_id)
    result = await db.execute(stmt)
    archive = result.unique().scalar_one_or_none()
    if not archive:
        online_resp = await crawler_client.post_safe(
            "/h5/goods/archive",
            {
                "archiveId": archive_id,
                "platformId": "741",
                "active": "6",
                "page": 1,
                "pageSize": 20,
                "sellStatus": 1,
                "dealType": "",
                "goodsType": "",
                "isPayBond": "",
                "startTime": "",
                "endTime": "",
                "fancyNumberType": "",
            },
        )
        online_data = online_resp.get("data") if online_resp else None
        if not isinstance(online_data, dict) or not online_data:
            return json.dumps({"error": f"藏品 {archive_id} 不存在"}, ensure_ascii=False)

        plane_code_json = online_data.get("planeCodeJson")
        archive_type = None
        if isinstance(plane_code_json, list) and plane_code_json:
            first = plane_code_json[0]
            if isinstance(first, dict):
                archive_type = first.get("name")

        issue_time = online_data.get("issueTime")
        return json.dumps({
            "archive_id": str(online_data.get("archiveId") or archive_id),
            "name": online_data.get("archiveName"),
            "type": archive_type,
            "total_count": online_data.get("totalGoodsCount"),
            "platform": online_data.get("platformName") or "鲸探",
            "ip": online_data.get("ipName"),
            "source_uid": online_data.get("ipId"),
            "issue_time": issue_time,
            "description": (online_data.get("archiveDescription") or "")[:200],
            "is_open_auction": bool(online_data.get("isOpenAuction")),
            "is_open_want_buy": bool(online_data.get("isOpenWantBuy")),
            "source": "online",
            "link": _archive_link(online_data.get("archiveId") or archive_id, online_data.get("platformId", 741)),
        }, ensure_ascii=False)
    return json.dumps({
        "archive_id": archive.archive_id,
        "name": archive.archive_name,
        "type": archive.archive_type,
        "total_count": archive.total_goods_count,
        "platform": archive.platform.name if archive.platform else None,
        "ip": archive.ip.ip_name if archive.ip else None,
        "ip_id": archive.ip_id,
        "issue_time": archive.issue_time.strftime("%Y-%m-%d %H:%M") if archive.issue_time else None,
        "description": (archive.archive_description or "")[:200],
        "is_open_auction": archive.is_open_auction,
        "is_open_want_buy": archive.is_open_want_buy,
        "source": "db",
        "link": _archive_link(archive.archive_id, archive.platform_id),
    }, ensure_ascii=False)


async def _search_ips(db: AsyncSession, **kwargs) -> str:
    keyword = str(kwargs.get("keyword", "") or "").strip()
    page = max(1, kwargs.get("page", 1))
    page_size = min(50, kwargs.get("page_size", 20))

    stmt = select(IP).options(selectinload(IP.platform))
    if keyword:
        normalized_keyword = keyword.lower()
        stmt = stmt.where(IP.ip_name.ilike(f"%{keyword}%")).order_by(
            case(
                (func.lower(IP.ip_name) == normalized_keyword, 0),
                (IP.ip_name.ilike(f"{keyword}%"), 1),
                else_=2,
            ),
            func.coalesce(IP.fans_count, 0).desc(),
            IP.id.desc(),
        )
    else:
        stmt = stmt.order_by(IP.id.desc())

    # 简化 COUNT 查询
    if keyword:
        count_stmt = select(func.count()).select_from(IP).where(IP.ip_name.ilike(f"%{keyword}%"))
    else:
        count_stmt = select(func.count()).select_from(IP)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    ips = result.unique().scalars().all()

    items = []
    for ip in ips:
        score, match_type = _ip_match_meta(ip.ip_name, keyword, ip.source_uid)
        items.append({
            "id": ip.id,
            "name": ip.ip_name,
            "platform": ip.platform.name if ip.platform else None,
            "fans_count": ip.fans_count,
            "description": (ip.description or "")[:100],
            "match_type": match_type if keyword else None,
            "match_label": _humanize_match_type(match_type) if keyword else None,
            "match_score": score if keyword else None,
            "source": "db",
            "source_label": _source_label("db"),
            "link": _ip_link(ip.source_uid, ip.from_type),
        })
    public_items = [_to_public_ip_item(item, index + 1) for index, item in enumerate(items[:5])]
    return json.dumps({
        "total": total,
        "page": page,
        "items": items,
        "public_items": public_items,
        "recommended_reply_format": {
            "style": "numbered_list",
            "instruction": "若用户还未明确具体IP，优先使用 public_items 按编号展示候选并让用户选择，不要暴露任何ID。",
        } if keyword and len(items) > 1 else None,
    }, ensure_ascii=False)


async def _online_search_archives(db: AsyncSession, **kwargs) -> str:
    keyword = str(kwargs.get("keyword", "") or "").strip()
    limit = min(20, max(1, int(kwargs.get("limit", 10))))
    if not keyword:
        return json.dumps({"error": "keyword 不能为空"}, ensure_ascii=False)
    items = await _fetch_online_archive_candidates(keyword, limit)
    public_items = [_to_public_archive_item(item, index + 1) for index, item in enumerate(items[:5])]
    return json.dumps({
        "keyword": keyword,
        "total": len(items),
        "items": items,
        "public_items": public_items,
        "clarification_question": "我查到一些在线藏品候选，请回复序号或名称确认你想看的对象。" if len(items) > 1 else None,
        "recommended_reply_format": {
            "style": "numbered_list",
            "instruction": "优先使用 public_items 按编号列出在线藏品候选，只显示名称和平台信息，再请用户确认；不要暴露任何ID或匹配元信息。",
        } if len(items) > 1 else None,
        "note": "这是在线藏品模糊查询结果，适合在数据库查不到或只有模糊命中时，先推荐给用户确认。",
    }, ensure_ascii=False)


async def _online_search_ips(db: AsyncSession, **kwargs) -> str:
    keyword = str(kwargs.get("keyword", "") or "").strip()
    limit = min(20, max(1, int(kwargs.get("limit", 10))))
    if not keyword:
        return json.dumps({"error": "keyword 不能为空"}, ensure_ascii=False)
    items = await _fetch_online_ip_candidates(keyword, limit)
    public_items = [_to_public_ip_item(item, index + 1) for index, item in enumerate(items[:5])]
    return json.dumps({
        "keyword": keyword,
        "total": len(items),
        "items": items,
        "public_items": public_items,
        "clarification_question": "我查到一些在线IP候选，请回复序号或名称确认你想看的对象。" if len(items) > 1 else None,
        "recommended_reply_format": {
            "style": "numbered_list",
            "instruction": "优先使用 public_items 按编号列出在线IP候选，只显示名称和平台信息，再请用户确认；不要暴露任何ID或匹配元信息。",
        } if len(items) > 1 else None,
        "note": "这是在线IP模糊查询结果，适合在数据库查不到或只有模糊命中时，先推荐给用户确认。",
    }, ensure_ascii=False)


async def _get_ip_detail(db: AsyncSession, **kwargs) -> str:
    ip_id = _coerce_int(kwargs.get("ip_id"))
    source_uid = _coerce_int(kwargs.get("source_uid"))
    if ip_id is None and source_uid is None:
        return json.dumps({"error": "ip_id 或 source_uid 至少提供一个"}, ensure_ascii=False)

    ip = None
    if ip_id is not None:
        stmt = select(IP).options(selectinload(IP.platform)).where(IP.id == ip_id)
        result = await db.execute(stmt)
        ip = result.unique().scalar_one_or_none()
    elif source_uid is not None:
        stmt = select(IP).options(selectinload(IP.platform)).where(IP.source_uid == source_uid)
        result = await db.execute(stmt)
        ip = result.unique().scalar_one_or_none()

    if not ip and source_uid is not None:
        online_resp = await crawler_client.post_safe(
            "/h5/community/userHome",
            {"uid": str(source_uid), "fromType": str(kwargs.get("from_type", 1))},
        )
        online_data = online_resp.get("data") if online_resp else None
        if isinstance(online_data, dict) and online_data:
            fans_count = None
            for key in ("fansCount", "fansNum", "fans", "followerCount", "followCount"):
                if online_data.get(key) is not None:
                    try:
                        fans_count = int(online_data.get(key))
                    except (TypeError, ValueError):
                        fans_count = None
                    break
            return json.dumps({
                "id": None,
                "name": online_data.get("nickname") or f"uid:{source_uid}",
                "platform": "鲸探",
                "fans_count": fans_count,
                "description": (online_data.get("description") or "")[:300],
                "archive_count": None,
                "source_uid": source_uid,
                "source": "online",
                "link": _ip_link(source_uid, kwargs.get("from_type", 1)),
                "archives": [],
            }, ensure_ascii=False)

    if not ip:
        target = ip_id if ip_id is not None else source_uid
        return json.dumps({"error": f"IP {target} 不存在"}, ensure_ascii=False)

    archive_stmt = select(Archive).where(Archive.ip_id == ip_id).order_by(Archive.archive_id.desc()).limit(20)
    archive_result = await db.execute(archive_stmt)
    archives = archive_result.scalars().all()

    count_stmt = select(func.count()).where(Archive.ip_id == ip_id)
    archive_count = (await db.execute(count_stmt)).scalar() or 0

    return json.dumps({
        "id": ip.id,
        "name": ip.ip_name,
        "platform": ip.platform.name if ip.platform else None,
        "fans_count": ip.fans_count,
        "description": (ip.description or "")[:300],
        "archive_count": archive_count,
        "source_uid": ip.source_uid,
        "source": "db",
        "link": _ip_link(ip.source_uid, ip.from_type),
        "archives": [
            {
                "archive_id": archive.archive_id,
                "name": archive.archive_name,
                "type": archive.archive_type,
                "link": _archive_link(archive.archive_id, archive.platform_id),
            }
            for archive in archives
        ],
    }, ensure_ascii=False)


async def _get_upcoming_launches(db: AsyncSession, **kwargs) -> str:
    days_ahead = kwargs.get("days_ahead", 7)
    days_back = kwargs.get("days_back", 3)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)
    end = now + timedelta(days=days_ahead)

    stmt = (
        select(LaunchCalendar)
        .options(selectinload(LaunchCalendar.platform), selectinload(LaunchCalendar.ip))
        .where(LaunchCalendar.sell_time.between(start, end))
        .order_by(LaunchCalendar.sell_time.asc())
        .limit(100)
    )
    result = await db.execute(stmt)
    items = result.unique().scalars().all()

    return json.dumps({
        "total": len(items),
        "note": "本接口无link字段，请勿为藏品名称添加任何链接",
        "items": [
            {
                "name": launch.name,
                "sell_time": launch.sell_time.strftime("%Y-%m-%d %H:%M") if launch.sell_time else None,
                "price": launch.price,
                "count": launch.count,
                "platform": launch.platform.name if launch.platform else None,
                "ip": launch.ip.ip_name if launch.ip else None,
            }
            for launch in items
        ],
    }, ensure_ascii=False)


async def _get_db_stats(db: AsyncSession, **kwargs) -> str:
    archive_count = (await db.execute(select(func.count()).select_from(Archive))).scalar() or 0
    ip_count = (await db.execute(select(func.count()).select_from(IP))).scalar() or 0
    platform_count = (await db.execute(select(func.count()).select_from(Platform))).scalar() or 0
    calendar_count = (await db.execute(select(func.count()).select_from(LaunchCalendar))).scalar() or 0
    plane_count = (await db.execute(select(func.count()).select_from(Plane))).scalar() or 0
    sku_wiki_count = (await db.execute(select(func.count()).select_from(JingtanSkuWiki))).scalar() or 0
    sku_detail_count = (await db.execute(select(func.count()).select_from(JingtanSkuHomepageDetail))).scalar() or 0

    latest_summary_stmt = select(MarketDailySummary).order_by(MarketDailySummary.stat_date.desc()).limit(1)
    latest_summary = (await db.execute(latest_summary_stmt)).scalar_one_or_none()
    market_summary = None
    if latest_summary:
        market_summary = {
            "date": str(latest_summary.stat_date),
            "total_deal_count": latest_summary.total_deal_count,
            "total_market_value": latest_summary.total_market_value,
            "total_deal_amount": latest_summary.total_deal_amount,
            "top_plane": latest_summary.top_plane_name,
            "top_ip": latest_summary.top_ip_name,
        }

    return json.dumps({
        "archive_count": archive_count,
        "ip_count": ip_count,
        "platform_count": platform_count,
        "launch_calendar_count": calendar_count,
        "plane_count": plane_count,
        "jingtan_sku_wiki_count": sku_wiki_count,
        "jingtan_sku_detail_count": sku_detail_count,
        "latest_market_summary": market_summary,
    }, ensure_ascii=False)


# ── 实时 API 工具 ────────────────────────────────────────

async def _get_archive_market(db: AsyncSession, **kwargs) -> str:
    archive_id = _coerce_int(kwargs.get("archive_id"))
    if archive_id is None:
        return json.dumps({"error": "archive_id 无效"}, ensure_ascii=False)

    time_type = kwargs.get("time_type", 0)
    resp = await crawler_client.post_safe(
        "/h5/archive/archiveMarket",
        {"timeType": time_type, "archiveId": archive_id},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取藏品行情失败"}, ensure_ascii=False)
    return json.dumps(resp.get("data", {}), ensure_ascii=False)


async def _get_archive_price_trend(db: AsyncSession, **kwargs) -> str:
    archive_id = _coerce_int(kwargs.get("archive_id"))
    if archive_id is None:
        return json.dumps({"error": "archive_id 无效"}, ensure_ascii=False)

    trend_type = kwargs.get("type", 1)
    resp = await crawler_client.post_safe(
        "/h5/archiveCensus/line",
        {"archiveId": archive_id, "type": trend_type},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取价格走势失败"}, ensure_ascii=False)
    data = resp.get("data", {})
    census_list = data.get("censusList", [])
    summary = {
        "avgPrice": data.get("avgPrice"),
        "dealPrice": data.get("dealPrice"),
        "minPrice": data.get("minPrice"),
        "dealCount": data.get("dealCount"),
        "trend_points": len(census_list),
        "recent": census_list[-10:] if len(census_list) > 10 else census_list,
    }
    return json.dumps(summary, ensure_ascii=False)


async def _get_sector_stats(db: AsyncSession, **kwargs) -> str:
    cache_key = make_cache_key("sector_stats")
    cached = await cache_get(cache_key)
    if cached:
        return cached

    resp = await crawler_client.post_safe(
        "/h5/plane/listNew",
        {"type": 0, "pageNum": 1, "pageSize": 100},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取板块统计失败"}, ensure_ascii=False)
    sectors = resp.get("data", [])
    items = []
    for sector in sectors:
        items.append({
            "id": sector.get("id"),
            "name": sector.get("name"),
            "avgPrice_change": sector.get("avgPrice"),
            "dealCount": sector.get("dealCount"),
            "shelvesRate": sector.get("shelvesRate"),
            "totalMarketValue": sector.get("totalMarketValue"),
        })
    result = json.dumps({"sectors": items, "note": "本接口无link字段，请勿添加链接"}, ensure_ascii=False)
    await cache_set(cache_key, result, ttl=300)
    return result


async def _get_hot_archives(db: AsyncSession, **kwargs) -> str:
    time_type = kwargs.get("time_type", 0)
    page = kwargs.get("page", 1)
    page_size = min(50, kwargs.get("page_size", 20))
    search_name = kwargs.get("search_name", "")

    cache_key = make_cache_key("hot_archives", time_type=time_type, page=page, page_size=page_size, search_name=search_name)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    payload = {
        "timeType": time_type,
        "pageNum": page,
        "pageSize": page_size,
        "dealCountSortType": False,
        "platformIdList": [],
        "communityIpIdList": [],
        "isAllPlatform": None,
        "isAllCommunityIp": None,
        "minPrice": None,
        "maxPrice": None,
        "beginTime": None,
        "endTime": None,
        "searchName": search_name,
        "planeCode": None,
        "topCode": "",
    }
    resp = await crawler_client.post_safe("/h5/market/marketArchivePage", payload)
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取成交热榜失败"}, ensure_ascii=False)
    data = resp.get("data", {})
    records = data.get("records", [])
    items = []
    for record in records:
        items.append({
            "archiveId": record.get("archiveId"),
            "name": record.get("archiveName"),
            "dealCount": record.get("dealCount"),
            "minAmount": record.get("minAmount"),
            "avgAmount": record.get("avgAmount"),
            "avgAmountRate": record.get("avgAmountRate"),
            "dealAmount": record.get("dealAmount"),
            "marketAmount": record.get("marketAmount"),
            "link": _archive_link(record.get("archiveId"), record.get("platformId", 741)),
        })
    result = json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)
    await cache_set(cache_key, result, ttl=180)
    return result


async def _get_market_categories(db: AsyncSession, **kwargs) -> str:
    cache_key = make_cache_key("market_categories")
    cached = await cache_get(cache_key)
    if cached:
        return cached

    resp = await crawler_client.post_safe("/h5/market/topList", {})
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取行情分类失败"}, ensure_ascii=False)
    categories = resp.get("data", [])
    items = []
    for category in categories:
        items.append({
            "id": category.get("id"),
            "name": category.get("name"),
            "code": category.get("code"),
            "showType": category.get("showType"),
        })
    result = json.dumps({"categories": items}, ensure_ascii=False)
    await cache_set(cache_key, result, ttl=600)
    return result


async def _get_category_archives(db: AsyncSession, **kwargs) -> str:
    top_code = kwargs.get("top_code", "")
    time_type = kwargs.get("time_type", 0)
    page = kwargs.get("page", 1)
    page_size = min(50, kwargs.get("page_size", 20))

    payload = {
        "timeType": time_type,
        "pageNum": page,
        "pageSize": page_size,
        "dealCountSortType": False,
        "platformIdList": [],
        "communityIpIdList": [],
        "searchName": "",
        "topCode": top_code,
    }
    resp = await crawler_client.post_safe("/h5/market/topArchivePage", payload)
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取分类排行失败"}, ensure_ascii=False)
    data = resp.get("data", {})
    records = data.get("records", [])
    items = []
    for record in records:
        items.append({
            "archiveId": record.get("archiveId"),
            "name": record.get("archiveName"),
            "dealCount": record.get("dealCount"),
            "minAmount": record.get("minAmount"),
            "avgAmount": record.get("avgAmount"),
            "marketAmount": record.get("marketAmount"),
            "dealAmount": record.get("dealAmount"),
            "link": _archive_link(record.get("archiveId"), record.get("platformId", 741)),
        })
    return json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)


async def _get_ip_ranking(db: AsyncSession, **kwargs) -> str:
    time_type = kwargs.get("time_type", 0)
    page = kwargs.get("page", 1)
    page_size = min(50, kwargs.get("page_size", 20))
    search_name = kwargs.get("search_name", "")

    cache_key = make_cache_key("ip_ranking", time_type=time_type, page=page, page_size=page_size, search_name=search_name)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    payload = {
        "timeType": time_type,
        "pageNum": page,
        "pageSize": page_size,
        "platformIdList": [],
        "communityIpIdList": [],
        "searchName": search_name,
    }
    resp = await crawler_client.post_safe("/h5/market/ipPage", payload)
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取IP排行失败"}, ensure_ascii=False)
    data = resp.get("data", {})
    records = data.get("records", [])

    items = []
    for record in records:
        community_ip_id = record.get("communityIpId")
        items.append({
            "name": record.get("name"),
            "communityIpId": community_ip_id,
            "archiveCount": record.get("archiveCount"),
            "marketAmount": record.get("marketAmount"),
            "marketAmountRate": record.get("marketAmountRate"),
            "hot": record.get("hot"),
            "dealCount": record.get("dealCount"),
            "avgAmount": record.get("avgAmount"),
            "link": _ip_link(community_ip_id, record.get("fromType", 1)),
        })
    result = json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)
    await cache_set(cache_key, result, ttl=300)
    return result


async def _get_plane_list(db: AsyncSession, **kwargs) -> str:
    cache_key = make_cache_key("plane_list")
    cached = await cache_get(cache_key)
    if cached:
        return cached

    resp = await crawler_client.get_safe("/h5/market/planeList")
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取板块列表失败"}, ensure_ascii=False)
    planes = resp.get("data", [])
    items = [{"name": plane.get("name"), "code": plane.get("code")} for plane in planes]
    result = json.dumps({"planes": items}, ensure_ascii=False)
    await cache_set(cache_key, result, ttl=600)
    return result


async def _get_sector_archives(db: AsyncSession, **kwargs) -> str:
    plane_code = kwargs.get("plane_code", "")
    time_type = kwargs.get("time_type", 0)
    page = kwargs.get("page", 1)
    page_size = min(50, kwargs.get("page_size", 20))
    search_name = kwargs.get("search_name", "")

    payload = {
        "timeType": time_type,
        "pageNum": page,
        "pageSize": page_size,
        "dealCountSortType": False,
        "platformIdList": [],
        "communityIpIdList": [],
        "searchName": search_name,
        "planeCode": plane_code,
        "topCode": "",
    }
    resp = await crawler_client.post_safe("/h5/market/marketArchivePage", payload)
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取板块交易详细失败"}, ensure_ascii=False)
    data = resp.get("data", {})
    records = data.get("records", [])
    items = []
    for record in records:
        items.append({
            "archiveId": record.get("archiveId"),
            "name": record.get("archiveName"),
            "dealCount": record.get("dealCount"),
            "minAmount": record.get("minAmount"),
            "avgAmount": record.get("avgAmount"),
            "avgAmountRate": record.get("avgAmountRate"),
            "dealAmount": record.get("dealAmount"),
            "marketAmount": record.get("marketAmount"),
            "marketAmountRate": record.get("marketAmountRate"),
            "salesAmount": record.get("salesAmount"),
            "overAmountRate": record.get("overAmountRate"),
            "link": _archive_link(record.get("archiveId"), record.get("platformId", 741)),
        })
    return json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)


# ── 市场概况 / 深度统计 / 鲸探SKU / 挂单 / 历史快照 ────

async def _get_market_overview(db: AsyncSession, **kwargs) -> str:
    """市场全局概况"""
    date_str = kwargs.get("date")
    if date_str:
        try:
            target_date = date_type.fromisoformat(date_str)
        except ValueError:
            return json.dumps({"error": "日期格式无效，请使用 YYYY-MM-DD"}, ensure_ascii=False)
    else:
        target_date = datetime.now(timezone.utc).date()

    stmt = select(MarketDailySummary).where(MarketDailySummary.stat_date == target_date)
    summary = (await db.execute(stmt)).scalar_one_or_none()

    if summary:
        prev_date = target_date - timedelta(days=1)
        prev_summary = (await db.execute(
            select(MarketDailySummary).where(MarketDailySummary.stat_date == prev_date)
        )).scalar_one_or_none()

        data = {
            "date": str(target_date),
            "total_deal_count": summary.total_deal_count,
            "total_market_value": summary.total_market_value,
            "total_deal_amount": summary.total_deal_amount,
            "active_plane_count": summary.active_plane_count,
            "top_plane": summary.top_plane_name,
            "top_plane_deal_count": summary.top_plane_deal_count,
            "top_ip": summary.top_ip_name,
            "top_ip_deal_count": summary.top_ip_deal_count,
            "source": "db",
        }
        if prev_summary:
            data["comparison"] = {
                "prev_date": str(prev_date),
                "deal_count_change": (summary.total_deal_count or 0) - (prev_summary.total_deal_count or 0),
                "market_value_change": round(((summary.total_market_value or 0) - (prev_summary.total_market_value or 0)), 2),
                "deal_amount_change": round(((summary.total_deal_amount or 0) - (prev_summary.total_deal_amount or 0)), 2),
            }
        return json.dumps(data, ensure_ascii=False)

    # DB 无数据，从在线板块统计汇总
    sector_resp = await crawler_client.post_safe("/h5/plane/listNew", {"type": 0, "pageNum": 1, "pageSize": 100})
    if not sector_resp or sector_resp.get("code") != 200:
        return json.dumps({"error": f"{target_date} 的市场概况暂无数据"}, ensure_ascii=False)

    sectors = sector_resp.get("data", [])
    total_market_value = sum(s.get("totalMarketValue") or 0 for s in sectors)
    total_deal_count = sum(s.get("dealCount") or 0 for s in sectors)
    top_sector = max(sectors, key=lambda s: s.get("dealCount") or 0) if sectors else {}

    return json.dumps({
        "date": str(target_date),
        "total_market_value": round(total_market_value, 2),
        "total_deal_count": total_deal_count,
        "active_plane_count": len([s for s in sectors if (s.get("dealCount") or 0) > 0]),
        "top_plane": top_sector.get("name"),
        "top_plane_deal_count": top_sector.get("dealCount"),
        "sectors_summary": [
            {
                "name": s.get("name"),
                "deal_count": s.get("dealCount"),
                "market_value": s.get("totalMarketValue"),
                "avg_price_change": s.get("avgPrice"),
            }
            for s in sorted(sectors, key=lambda x: x.get("dealCount") or 0, reverse=True)[:10]
        ],
        "source": "online_aggregated",
    }, ensure_ascii=False)


async def _get_plane_census(db: AsyncSession, **kwargs) -> str:
    """板块详细成交统计（涨跌分布）"""
    plane_code = kwargs.get("plane_code", "")
    time_type = kwargs.get("time_type", 0)

    resp = await crawler_client.post_safe(
        "/h5/market/censusPlaneArchive",
        {"timeType": time_type, "planeCode": plane_code},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取板块成交统计失败"}, ensure_ascii=False)

    data = resp.get("data", {})
    up_down_list = data.get("upDownList", [])
    up_dist = [{"range": i.get("label"), "count": i.get("count")} for i in up_down_list if i.get("type") == 1]
    down_dist = [{"range": i.get("label"), "count": i.get("count")} for i in up_down_list if i.get("type") == 2]

    return json.dumps({
        "plane_code": plane_code,
        "total_market_value": data.get("totalMarketAmount"),
        "market_value_change_pct": data.get("totalMarketAmountRate"),
        "total_deal_count": data.get("totalDealCount"),
        "deal_count_change_pct": data.get("totalDealCountRate"),
        "total_archive_count": data.get("totalArchiveCount"),
        "up_count": data.get("upArchiveCount"),
        "down_count": data.get("downArchiveCount"),
        "up_distribution": up_dist,
        "down_distribution": down_dist,
    }, ensure_ascii=False)


async def _get_top_census(db: AsyncSession, **kwargs) -> str:
    """行情分类详细成交统计（涨跌分布）"""
    top_code = kwargs.get("top_code", "")
    time_type = kwargs.get("time_type", 0)

    resp = await crawler_client.post_safe(
        "/h5/market/censusArchiveTop",
        {"timeType": time_type, "topCode": top_code},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取分类成交统计失败"}, ensure_ascii=False)

    data = resp.get("data", {})
    up_down_list = data.get("upDownList", [])
    up_dist = [{"range": i.get("label"), "count": i.get("count")} for i in up_down_list if i.get("type") == 1]
    down_dist = [{"range": i.get("label"), "count": i.get("count")} for i in up_down_list if i.get("type") == 2]

    return json.dumps({
        "top_code": top_code,
        "total_market_value": data.get("totalMarketAmount"),
        "market_value_change_pct": data.get("totalMarketAmountRate"),
        "total_deal_count": data.get("totalDealCount"),
        "deal_count_change_pct": data.get("totalDealCountRate"),
        "total_archive_count": data.get("totalArchiveCount"),
        "up_count": data.get("upArchiveCount"),
        "down_count": data.get("downArchiveCount"),
        "up_distribution": up_dist,
        "down_distribution": down_dist,
    }, ensure_ascii=False)


async def _get_archive_goods_listing(db: AsyncSession, **kwargs) -> str:
    """获取藏品二级市场挂单列表"""
    archive_id = _coerce_int(kwargs.get("archive_id"))
    if archive_id is None:
        return json.dumps({"error": "archive_id 无效"}, ensure_ascii=False)

    page = kwargs.get("page", 1)
    page_size = min(20, kwargs.get("page_size", 20))

    resp = await crawler_client.post_safe(
        "/h5/goods/archiveGoods",
        {
            "archiveId": str(archive_id),
            "platformId": "741",
            "active": "0",
            "page": page,
            "pageSize": page_size,
            "sellStatus": 2,
            "dealType": "",
            "goodsType": "",
            "isPayBond": "",
            "startTime": "",
            "endTime": "",
            "fancyNumberType": "",
        },
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取挂单列表失败"}, ensure_ascii=False)

    data = resp.get("data", {})
    if isinstance(data, list):
        records = data
        total = len(data)
    else:
        records = data.get("list") or data.get("records") or []
        total = data.get("total") or len(records)

    items = []
    for record in records[:page_size]:
        items.append({
            "goods_no": record.get("goodsNo"),
            "price": record.get("price"),
            "sell_time": record.get("upTime") or record.get("sellTime"),
            "goods_type": record.get("goodsTypeName") or record.get("goodsType"),
        })

    return json.dumps({
        "archive_id": archive_id,
        "total": total,
        "items": items,
        "link": _archive_link(archive_id),
    }, ensure_ascii=False)


async def _search_jingtan_sku(db: AsyncSession, **kwargs) -> str:
    """搜索鲸探SKU百科"""
    keyword = str(kwargs.get("keyword", "") or "").strip()
    category = str(kwargs.get("category", "") or "").strip()
    page = max(1, kwargs.get("page", 1))
    page_size = min(50, kwargs.get("page_size", 20))

    filters = []
    if keyword:
        filters.append(or_(
            JingtanSkuWiki.sku_name.ilike(f"%{keyword}%"),
            JingtanSkuWiki.author.ilike(f"%{keyword}%"),
        ))
    if category:
        filters.append(or_(
            JingtanSkuWiki.first_category_name.ilike(f"%{category}%"),
            JingtanSkuWiki.second_category_name.ilike(f"%{category}%"),
        ))

    count_stmt = select(func.count()).select_from(JingtanSkuWiki)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(JingtanSkuWiki)
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(JingtanSkuWiki.sku_issue_time_ms.desc().nullslast()).offset((page - 1) * page_size).limit(page_size)
    skus = (await db.execute(stmt)).scalars().all()

    items = []
    for sku in skus:
        issue_time = None
        if sku.sku_issue_time_ms:
            try:
                issue_time = datetime.fromtimestamp(sku.sku_issue_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            except (OSError, ValueError):
                pass
        items.append({
            "sku_id": sku.sku_id,
            "name": sku.sku_name,
            "author": sku.author,
            "owner": sku.owner,
            "first_category": sku.first_category_name,
            "second_category": sku.second_category_name,
            "quantity": sku.sku_quantity,
            "issue_time": issue_time,
        })

    return json.dumps({"total": total, "page": page, "items": items}, ensure_ascii=False)


async def _get_jingtan_sku_detail(db: AsyncSession, **kwargs) -> str:
    """获取鲸探SKU详情"""
    sku_id = str(kwargs.get("sku_id", "") or "").strip()
    if not sku_id:
        return json.dumps({"error": "sku_id 不能为空"}, ensure_ascii=False)

    detail = (await db.execute(
        select(JingtanSkuHomepageDetail).where(JingtanSkuHomepageDetail.sku_id == sku_id)
    )).scalar_one_or_none()

    if detail:
        issue_time = None
        if detail.sku_issue_time_ms:
            try:
                issue_time = datetime.fromtimestamp(detail.sku_issue_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            except (OSError, ValueError):
                pass
        return json.dumps({
            "sku_id": detail.sku_id,
            "name": detail.sku_name,
            "author": detail.author,
            "owner": detail.owner,
            "partner_name": detail.partner_name,
            "description": (detail.sku_desc or "")[:500],
            "quantity": detail.sku_quantity,
            "quantity_type": detail.quantity_type,
            "issue_time": issue_time,
            "collect_count": detail.collect_num,
            "comment_count": detail.comment_num,
            "producer_name": detail.producer_name,
            "certification_name": detail.certification_name,
            "produce_amount": detail.produce_amount,
            "source": "db",
        }, ensure_ascii=False)

    wiki = (await db.execute(
        select(JingtanSkuWiki).where(JingtanSkuWiki.sku_id == sku_id)
    )).scalar_one_or_none()

    if wiki:
        issue_time = None
        if wiki.sku_issue_time_ms:
            try:
                issue_time = datetime.fromtimestamp(wiki.sku_issue_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            except (OSError, ValueError):
                pass
        return json.dumps({
            "sku_id": wiki.sku_id,
            "name": wiki.sku_name,
            "author": wiki.author,
            "owner": wiki.owner,
            "partner_name": wiki.partner_name,
            "first_category": wiki.first_category_name,
            "second_category": wiki.second_category_name,
            "quantity": wiki.sku_quantity,
            "issue_time": issue_time,
            "source": "wiki",
        }, ensure_ascii=False)

    return json.dumps({"error": f"SKU {sku_id} 不存在"}, ensure_ascii=False)


async def _get_market_history(db: AsyncSession, **kwargs) -> str:
    """查询历史市场快照"""
    snapshot_type = kwargs.get("snapshot_type", "plane")
    date_str = kwargs.get("date", "")
    compare_date_str = kwargs.get("compare_date")
    limit = min(50, max(1, int(kwargs.get("limit", 20))))

    try:
        target_date = date_type.fromisoformat(date_str)
    except (ValueError, TypeError):
        return json.dumps({"error": "date 格式无效，请使用 YYYY-MM-DD"}, ensure_ascii=False)

    compare_date = None
    if compare_date_str:
        try:
            compare_date = date_type.fromisoformat(compare_date_str)
        except ValueError:
            pass

    if snapshot_type == "plane":
        plane_code = kwargs.get("plane_code")
        stmt = select(MarketPlaneSnapshot).where(MarketPlaneSnapshot.stat_date == target_date)
        if plane_code:
            stmt = stmt.where(MarketPlaneSnapshot.plane_code == plane_code)
        stmt = stmt.order_by(MarketPlaneSnapshot.total_market_value.desc().nullslast()).limit(limit)
        snapshots = (await db.execute(stmt)).scalars().all()

        items = [{
            "name": s.plane_name, "code": s.plane_code,
            "avg_price_change": s.avg_price, "deal_count": s.deal_count,
            "shelves_rate": s.shelves_rate, "market_value": s.total_market_value,
        } for s in snapshots]

        compare_items = None
        if compare_date:
            c_stmt = select(MarketPlaneSnapshot).where(MarketPlaneSnapshot.stat_date == compare_date)
            if plane_code:
                c_stmt = c_stmt.where(MarketPlaneSnapshot.plane_code == plane_code)
            c_stmt = c_stmt.order_by(MarketPlaneSnapshot.total_market_value.desc().nullslast()).limit(limit)
            compare_items = [{
                "name": s.plane_name, "avg_price_change": s.avg_price,
                "deal_count": s.deal_count, "market_value": s.total_market_value,
            } for s in (await db.execute(c_stmt)).scalars().all()]

        return json.dumps({
            "type": "plane", "date": str(target_date), "items": items,
            "compare_date": str(compare_date) if compare_date else None,
            "compare_items": compare_items,
        }, ensure_ascii=False)

    elif snapshot_type == "ip":
        stmt = (
            select(MarketIPSnapshot)
            .where(MarketIPSnapshot.stat_date == target_date)
            .order_by(MarketIPSnapshot.rank.asc().nullslast())
            .limit(limit)
        )
        snapshots = (await db.execute(stmt)).scalars().all()

        items = [{
            "rank": s.rank, "name": s.name,
            "archive_count": s.archive_count, "market_value": s.market_amount,
            "market_value_change": s.market_amount_rate, "hot": s.hot,
            "deal_count": s.deal_count, "avg_price": s.avg_amount,
        } for s in snapshots]

        compare_items = None
        if compare_date:
            c_stmt = (
                select(MarketIPSnapshot)
                .where(MarketIPSnapshot.stat_date == compare_date)
                .order_by(MarketIPSnapshot.rank.asc().nullslast())
                .limit(limit)
            )
            compare_items = [{
                "rank": s.rank, "name": s.name,
                "market_value": s.market_amount, "deal_count": s.deal_count,
            } for s in (await db.execute(c_stmt)).scalars().all()]

        return json.dumps({
            "type": "ip", "date": str(target_date), "items": items,
            "compare_date": str(compare_date) if compare_date else None,
            "compare_items": compare_items,
        }, ensure_ascii=False)

    elif snapshot_type == "archive":
        top_code = kwargs.get("top_code", "")
        stmt = select(MarketArchiveSnapshot).where(MarketArchiveSnapshot.stat_date == target_date)
        if top_code:
            stmt = stmt.where(MarketArchiveSnapshot.top_code == top_code)
        stmt = stmt.order_by(MarketArchiveSnapshot.rank.asc().nullslast()).limit(limit)
        snapshots = (await db.execute(stmt)).scalars().all()

        items = [{
            "rank": s.rank, "name": s.archive_name, "top_name": s.top_name,
            "deal_count": s.deal_count, "market_value": s.market_amount,
            "market_value_change": s.market_amount_rate,
            "min_price": s.min_amount, "avg_price": s.avg_amount,
            "deal_amount": s.deal_amount, "publish_count": s.publish_count,
            "link": _archive_link(s.archive_id, s.platform_id),
        } for s in snapshots]

        compare_items = None
        if compare_date:
            c_stmt = select(MarketArchiveSnapshot).where(MarketArchiveSnapshot.stat_date == compare_date)
            if top_code:
                c_stmt = c_stmt.where(MarketArchiveSnapshot.top_code == top_code)
            c_stmt = c_stmt.order_by(MarketArchiveSnapshot.rank.asc().nullslast()).limit(limit)
            compare_items = [{
                "rank": s.rank, "name": s.archive_name,
                "market_value": s.market_amount, "min_price": s.min_amount,
                "deal_count": s.deal_count,
            } for s in (await db.execute(c_stmt)).scalars().all()]

        return json.dumps({
            "type": "archive", "date": str(target_date), "top_code": top_code or "all",
            "items": items,
            "compare_date": str(compare_date) if compare_date else None,
            "compare_items": compare_items,
        }, ensure_ascii=False)

    return json.dumps({"error": f"不支持的快照类型: {snapshot_type}"}, ensure_ascii=False)


async def _get_launch_detail(db: AsyncSession, **kwargs) -> str:
    """获取发行详情"""
    launch_id = _coerce_int(kwargs.get("launch_id"))
    source_id = kwargs.get("source_id")

    if launch_id is None and not source_id:
        return json.dumps({"error": "launch_id 或 source_id 至少提供一个"}, ensure_ascii=False)

    if launch_id:
        stmt = (
            select(LaunchCalendar)
            .options(selectinload(LaunchCalendar.platform), selectinload(LaunchCalendar.ip), selectinload(LaunchCalendar.detail))
            .where(LaunchCalendar.id == launch_id)
        )
    else:
        stmt = (
            select(LaunchCalendar)
            .options(selectinload(LaunchCalendar.platform), selectinload(LaunchCalendar.ip), selectinload(LaunchCalendar.detail))
            .where(LaunchCalendar.source_id == source_id)
        )

    launch = (await db.execute(stmt)).unique().scalar_one_or_none()
    if not launch:
        return json.dumps({"error": "发行记录不存在"}, ensure_ascii=False)

    data = {
        "id": launch.id,
        "name": launch.name,
        "sell_time": launch.sell_time.strftime("%Y-%m-%d %H:%M") if launch.sell_time else None,
        "price": launch.price,
        "count": launch.count,
        "platform": launch.platform.name if launch.platform else None,
        "ip": launch.ip.ip_name if launch.ip else None,
        "is_priority_purchase": launch.is_priority_purchase,
        "priority_purchase_num": launch.priority_purchase_num,
    }

    if launch.detail:
        detail = launch.detail
        data.update({
            "priority_purchase_time": detail.priority_purchase_time.strftime("%Y-%m-%d %H:%M") if detail.priority_purchase_time else None,
            "context_condition": detail.context_condition,
            "status": detail.status,
        })

    return json.dumps(data, ensure_ascii=False)


# ── 执行器映射 ────────────────────────────────────────

EXECUTORS = {
    "search_archives": _search_archives,
    "resolve_entities": _resolve_entities,
    "get_archive_detail": _get_archive_detail,
    "search_ips": _search_ips,
    "online_search_archives": _online_search_archives,
    "online_search_ips": _online_search_ips,
    "get_ip_detail": _get_ip_detail,
    "get_upcoming_launches": _get_upcoming_launches,
    "get_db_stats": _get_db_stats,
    "get_archive_market": _get_archive_market,
    "get_archive_price_trend": _get_archive_price_trend,
    "get_sector_stats": _get_sector_stats,
    "get_hot_archives": _get_hot_archives,
    "get_market_categories": _get_market_categories,
    "get_category_archives": _get_category_archives,
    "get_ip_ranking": _get_ip_ranking,
    "get_plane_list": _get_plane_list,
    "get_sector_archives": _get_sector_archives,
    "get_market_overview": _get_market_overview,
    "get_plane_census": _get_plane_census,
    "get_top_census": _get_top_census,
    "get_archive_goods_listing": _get_archive_goods_listing,
    "search_jingtan_sku": _search_jingtan_sku,
    "get_jingtan_sku_detail": _get_jingtan_sku_detail,
    "get_market_history": _get_market_history,
    "get_launch_detail": _get_launch_detail,
}


async def execute_tool(name: str, arguments: dict, db: AsyncSession) -> str:
    """执行工具并返回结果字符串"""
    executor = EXECUTORS.get(name)
    if not executor:
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    try:
        return await executor(db, **arguments)
    except Exception as e:
        logger.exception(f"Tool {name} 执行失败")
        return json.dumps({"error": f"工具执行失败: {str(e)}"}, ensure_ascii=False)

