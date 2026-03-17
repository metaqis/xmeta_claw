"""Tool 执行器：名称 → 执行函数映射"""
import json
import re
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crawler.client import crawler_client
from app.database.models import Archive, IP, LaunchCalendar, Platform
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
        "source_label": item.get("source_label"),
        "match_label": item.get("match_label"),
        "platform": item.get("platform"),
        "ip": item.get("ip"),
        "selection_label": item.get("selection_label"),
    }


def _to_public_archive_item(item: dict[str, Any], index: int | None = None) -> dict[str, Any]:
    public_item = {
        "name": item.get("name"),
        "type": item.get("type"),
        "platform": item.get("platform"),
        "ip": item.get("ip"),
        "issue_time": item.get("issue_time"),
        "match_label": item.get("match_label"),
        "source_label": item.get("source_label"),
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
        "match_label": item.get("match_label"),
        "source_label": item.get("source_label"),
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
            "instruction": "按 1、2、3 编号列出候选，每项包含名称、来源、匹配方式；结尾请用户回复序号或名称。",
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
        "note": "当用户输入不完整或只有模糊名称时，优先从 public_recommendations 中给出候选让用户选择；若数据库无结果，可参考 online_archives / online_ips 继续推荐。回复时不要暴露任何ID。",
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
            "instruction": "优先使用 public_items 按编号列出在线藏品候选，补充来源和匹配方式，再请用户确认；不要暴露任何ID。",
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
            "instruction": "优先使用 public_items 按编号列出在线IP候选，补充来源和匹配方式，再请用户确认；不要暴露任何ID。",
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
    now = datetime.utcnow()
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

    return json.dumps({
        "archive_count": archive_count,
        "ip_count": ip_count,
        "platform_count": platform_count,
        "launch_calendar_count": calendar_count,
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
        "searchName": search_name,
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
