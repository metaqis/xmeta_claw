"""Tool 执行器：名称 → 执行函数映射"""
import json
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crawler.client import crawler_client
from app.database.models import Archive, IP, Platform, LaunchCalendar

XMETA_BASE = "https://xmeta.x-metash.cn/prod/xmeta_mall/#/pages"


def _archive_link(archive_id, platform_id=741) -> str:
    return f"{XMETA_BASE}/salesDetail/index?archiveId={archive_id}&platformId={platform_id or 741}&active=6"


def _ip_link(source_uid, from_type=1) -> str | None:
    if source_uid is None:
        return None
    return f"{XMETA_BASE}/ltwd/index?uid={source_uid}&fromType={from_type or 1}"


# ── DB 工具 ──────────────────────────────────────────────────

async def _search_archives(db: AsyncSession, **kwargs) -> str:
    keyword = kwargs.get("keyword", "")
    platform_id = kwargs.get("platform_id")
    page = max(1, kwargs.get("page", 1))
    page_size = min(50, kwargs.get("page_size", 20))

    stmt = select(Archive).options(
        selectinload(Archive.platform), selectinload(Archive.ip)
    )
    if keyword:
        stmt = stmt.where(
            or_(
                Archive.archive_name.ilike(f"%{keyword}%"),
                Archive.ip.has(IP.ip_name.ilike(f"%{keyword}%")),
            )
        )
    if platform_id:
        stmt = stmt.where(Archive.platform_id == platform_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Archive.archive_id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    archives = result.unique().scalars().all()

    items = []
    for a in archives:
        items.append({
            "archive_id": a.archive_id,
            "name": a.archive_name,
            "type": a.archive_type,
            "total_count": a.total_goods_count,
            "platform": a.platform.name if a.platform else None,
            "ip": a.ip.ip_name if a.ip else None,
            "issue_time": a.issue_time.strftime("%Y-%m-%d") if a.issue_time else None,
            "link": _archive_link(a.archive_id, a.platform_id),
        })
    return json.dumps({"total": total, "page": page, "items": items}, ensure_ascii=False)


async def _get_archive_detail(db: AsyncSession, **kwargs) -> str:
    archive_id = str(kwargs.get("archive_id", ""))
    stmt = select(Archive).options(
        selectinload(Archive.platform), selectinload(Archive.ip)
    ).where(Archive.archive_id == archive_id)
    result = await db.execute(stmt)
    a = result.unique().scalar_one_or_none()
    if not a:
        return json.dumps({"error": f"藏品 {archive_id} 不存在"}, ensure_ascii=False)
    return json.dumps({
        "archive_id": a.archive_id,
        "name": a.archive_name,
        "type": a.archive_type,
        "total_count": a.total_goods_count,
        "platform": a.platform.name if a.platform else None,
        "ip": a.ip.ip_name if a.ip else None,
        "ip_id": a.ip_id,
        "issue_time": a.issue_time.strftime("%Y-%m-%d %H:%M") if a.issue_time else None,
        "description": (a.archive_description or "")[:200],
        "is_open_auction": a.is_open_auction,
        "is_open_want_buy": a.is_open_want_buy,
        "link": _archive_link(a.archive_id, a.platform_id),
    }, ensure_ascii=False)


async def _search_ips(db: AsyncSession, **kwargs) -> str:
    keyword = kwargs.get("keyword", "")
    page = max(1, kwargs.get("page", 1))
    page_size = min(50, kwargs.get("page_size", 20))

    stmt = select(IP).options(selectinload(IP.platform))
    if keyword:
        stmt = stmt.where(IP.ip_name.ilike(f"%{keyword}%"))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(IP.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    ips = result.unique().scalars().all()

    items = []
    for ip in ips:
        items.append({
            "id": ip.id,
            "name": ip.ip_name,
            "platform": ip.platform.name if ip.platform else None,
            "fans_count": ip.fans_count,
            "description": (ip.description or "")[:100],
            "link": _ip_link(ip.source_uid, ip.from_type),
        })
    return json.dumps({"total": total, "page": page, "items": items}, ensure_ascii=False)


async def _get_ip_detail(db: AsyncSession, **kwargs) -> str:
    ip_id = kwargs.get("ip_id")
    stmt = select(IP).options(selectinload(IP.platform)).where(IP.id == ip_id)
    result = await db.execute(stmt)
    ip = result.unique().scalar_one_or_none()
    if not ip:
        return json.dumps({"error": f"IP {ip_id} 不存在"}, ensure_ascii=False)

    # 获取旗下藏品数量和列表
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
        "link": _ip_link(ip.source_uid, ip.from_type),
        "archives": [
            {
                "archive_id": a.archive_id,
                "name": a.archive_name,
                "type": a.archive_type,
                "link": _archive_link(a.archive_id, a.platform_id),
            }
            for a in archives
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
                "name": lc.name,
                "sell_time": lc.sell_time.strftime("%Y-%m-%d %H:%M") if lc.sell_time else None,
                "price": lc.price,
                "count": lc.count,
                "platform": lc.platform.name if lc.platform else None,
                "ip": lc.ip.ip_name if lc.ip else None,
            }
            for lc in items
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
    archive_id = kwargs.get("archive_id")
    time_type = kwargs.get("time_type", 0)
    resp = await crawler_client.post_safe(
        "/h5/archive/archiveMarket",
        {"timeType": time_type, "archiveId": archive_id},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取藏品行情失败"}, ensure_ascii=False)
    return json.dumps(resp.get("data", {}), ensure_ascii=False)


async def _get_archive_price_trend(db: AsyncSession, **kwargs) -> str:
    archive_id = kwargs.get("archive_id")
    trend_type = kwargs.get("type", 1)
    resp = await crawler_client.post_safe(
        "/h5/archiveCensus/line",
        {"archiveId": archive_id, "type": trend_type},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取价格走势失败"}, ensure_ascii=False)
    data = resp.get("data", {})
    # 精简数据：只返回汇总 + 最近10条
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
    resp = await crawler_client.post_safe(
        "/h5/plane/listNew",
        {"type": 0, "pageNum": 1, "pageSize": 100},
    )
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取板块统计失败"}, ensure_ascii=False)
    sectors = resp.get("data", [])
    items = []
    for s in sectors:
        items.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "avgPrice_change": s.get("avgPrice"),
            "dealCount": s.get("dealCount"),
            "shelvesRate": s.get("shelvesRate"),
            "totalMarketValue": s.get("totalMarketValue"),
        })
    return json.dumps({"sectors": items, "note": "本接口无link字段，请勿添加链接"}, ensure_ascii=False)


async def _get_hot_archives(db: AsyncSession, **kwargs) -> str:
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
        "topCode": "",
    }
    resp = await crawler_client.post_safe("/h5/market/marketArchivePage", payload)
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取成交热榜失败"}, ensure_ascii=False)
    data = resp.get("data", {})
    records = data.get("records", [])
    items = []
    for r in records:
        items.append({
            "archiveId": r.get("archiveId"),
            "name": r.get("archiveName"),
            "dealCount": r.get("dealCount"),
            "minAmount": r.get("minAmount"),
            "avgAmount": r.get("avgAmount"),
            "avgAmountRate": r.get("avgAmountRate"),
            "dealAmount": r.get("dealAmount"),
            "marketAmount": r.get("marketAmount"),
            "link": _archive_link(r.get("archiveId"), r.get("platformId", 741)),
        })
    return json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)


async def _get_market_categories(db: AsyncSession, **kwargs) -> str:
    resp = await crawler_client.post_safe("/h5/market/topList", {})
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取行情分类失败"}, ensure_ascii=False)
    categories = resp.get("data", [])
    items = []
    for c in categories:
        items.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "code": c.get("code"),
            "showType": c.get("showType"),
        })
    return json.dumps({"categories": items}, ensure_ascii=False)


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
    for r in records:
        items.append({
            "archiveId": r.get("archiveId"),
            "name": r.get("archiveName"),
            "dealCount": r.get("dealCount"),
            "minAmount": r.get("minAmount"),
            "avgAmount": r.get("avgAmount"),
            "marketAmount": r.get("marketAmount"),
            "dealAmount": r.get("dealAmount"),
            "link": _archive_link(r.get("archiveId"), r.get("platformId", 741)),
        })
    return json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)


async def _get_ip_ranking(db: AsyncSession, **kwargs) -> str:
    time_type = kwargs.get("time_type", 0)
    page = kwargs.get("page", 1)
    page_size = min(50, kwargs.get("page_size", 20))
    search_name = kwargs.get("search_name", "")

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
    for r in records:
        cid = r.get("communityIpId")
        items.append({
            "name": r.get("name"),
            "communityIpId": cid,
            "archiveCount": r.get("archiveCount"),
            "marketAmount": r.get("marketAmount"),
            "marketAmountRate": r.get("marketAmountRate"),
            "hot": r.get("hot"),
            "dealCount": r.get("dealCount"),
            "avgAmount": r.get("avgAmount"),
            "link": _ip_link(cid, r.get("fromType", 1)),
        })
    return json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)


async def _get_plane_list(db: AsyncSession, **kwargs) -> str:
    resp = await crawler_client.get_safe("/h5/market/planeList")
    if not resp or resp.get("code") != 200:
        return json.dumps({"error": "获取板块列表失败"}, ensure_ascii=False)
    planes = resp.get("data", [])
    items = [{"name": p.get("name"), "code": p.get("code")} for p in planes]
    return json.dumps({"planes": items}, ensure_ascii=False)


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
    for r in records:
        items.append({
            "archiveId": r.get("archiveId"),
            "name": r.get("archiveName"),
            "dealCount": r.get("dealCount"),
            "minAmount": r.get("minAmount"),
            "avgAmount": r.get("avgAmount"),
            "avgAmountRate": r.get("avgAmountRate"),
            "dealAmount": r.get("dealAmount"),
            "marketAmount": r.get("marketAmount"),
            "marketAmountRate": r.get("marketAmountRate"),
            "salesAmount": r.get("salesAmount"),
            "overAmountRate": r.get("overAmountRate"),
            "link": _archive_link(r.get("archiveId"), r.get("platformId", 741)),
        })
    return json.dumps({"total": data.get("total", 0), "items": items}, ensure_ascii=False)


# ── 执行器映射 ────────────────────────────────────────

EXECUTORS = {
    "search_archives": _search_archives,
    "get_archive_detail": _get_archive_detail,
    "search_ips": _search_ips,
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
