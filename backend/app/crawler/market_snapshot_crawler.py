"""市场快照爬虫 — 每日 23:50 执行，抓取板块/IP/热门藏品三维数据并写入快照表"""
from datetime import date, datetime
from typing import Callable, Awaitable, Optional

from loguru import logger
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
import json

from app.database.models import (
    MarketDailySummary,
    MarketPlaneSnapshot,
    MarketIPSnapshot,
    MarketArchiveSnapshot,
    MarketPlaneCensus,
    MarketTopCensus,
)

# 只抓取这几个行情分类（code 来自 /h5/market/topList 接口）
# 使用 None 表示「由接口动态获取」，不硬编码白名单
_TOP_LIST_MAX_CATEGORIES = 10   # 最多抓几个分类
_IP_PAGE_SIZE = 50              # 每次抓 Top 50 个 IP
_ARCHIVE_PAGE_SIZE = 50         # 每个分类取前 50 条


async def crawl_plane_snapshots(
    db: AsyncSession,
    stat_date: date,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> int:
    """抓取板块列表实时统计数据，写入 market_plane_snapshots"""

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    data = await crawler_client.post_safe("/h5/plane/listNew", {"type": 0, "pageNum": 1, "pageSize": 100})
    if not data:
        await _log("板块列表请求失败，跳过")
        return 0

    records = data.get("data") or []
    if not records:
        await _log("板块列表数据为空，跳过")
        return 0

    rows = []
    for item in records:
        rows.append(
            MarketPlaneSnapshot(
                stat_date=stat_date,
                plane_source_id=item.get("id"),
                plane_code=str(item.get("code", "")),
                plane_name=str(item.get("name", "")),
                avg_price=item.get("avgPrice"),
                deal_price=item.get("dealPrice"),
                deal_count=item.get("dealCount"),
                shelves_rate=item.get("shelvesRate"),
                total_market_value=item.get("totalMarketValue"),
            )
        )

    db.add_all(rows)
    await db.commit()
    await _log(f"板块快照写入完成: {len(rows)} 条")
    return len(rows)


async def crawl_ip_snapshots(
    db: AsyncSession,
    stat_date: date,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> int:
    """抓取 IP 排行榜数据，写入 market_ip_snapshots（取 Top N）"""

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    data = await crawler_client.post_safe(
        "/h5/market/ipPage",
        {
            "timeType": 0,
            "pageNum": 1,
            "pageSize": _IP_PAGE_SIZE,
            "platformIdList": [],
            "communityIpIdList": [],
            "isAllPlatform": None,
            "isAllCommunityIp": None,
            "minPrice": None,
            "maxPrice": None,
            "beginTime": None,
            "endTime": None,
            "searchName": "",
            "planeCode": None,
        },
    )
    if not data:
        await _log("IP 排行榜请求失败，跳过")
        return 0

    records = (data.get("data") or {}).get("records") or []
    if not records:
        await _log("IP 排行榜数据为空，跳过")
        return 0

    rows = []
    for rank, item in enumerate(records, start=1):
        rows.append(
            MarketIPSnapshot(
                stat_date=stat_date,
                community_ip_id=item.get("communityIpId"),
                name=str(item.get("name", "")),
                avatar=item.get("avatar"),
                rank=rank,
                archive_count=item.get("archiveCount"),
                market_amount=item.get("marketAmount"),
                market_amount_rate=item.get("marketAmountRate"),
                hot=item.get("hot"),
                hot_rate=item.get("hotRate"),
                avg_amount=item.get("avgAmount"),
                avg_amount_rate=item.get("avgAmountRate"),
                deal_count=item.get("dealCount"),
                deal_count_rate=item.get("dealCountRate"),
                publish_count=item.get("publishCount"),
            )
        )

    db.add_all(rows)
    await db.commit()
    await _log(f"IP 快照写入完成: {len(rows)} 条")
    return len(rows)


async def crawl_archive_snapshots(
    db: AsyncSession,
    stat_date: date,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> int:
    """抓取各行情分类下热门成交藏品，写入 market_archive_snapshots"""

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    # 1. 获取分类列表
    cat_data = await crawler_client.post_safe("/h5/market/topList", {})
    if not cat_data:
        await _log("行情分类列表请求失败，跳过")
        return 0

    categories = (cat_data.get("data") or [])[:_TOP_LIST_MAX_CATEGORIES]
    if not categories:
        await _log("行情分类为空，跳过")
        return 0

    await _log(f"获取到 {len(categories)} 个行情分类，开始抓取热门藏品")

    total = 0
    for cat in categories:
        top_code = str(cat.get("code", ""))
        top_name = str(cat.get("name", ""))
        if not top_code:
            continue

        arch_data = await crawler_client.post_safe(
            "/h5/market/topArchivePage",
            {
                "timeType": 0,
                "pageNum": 1,
                "pageSize": _ARCHIVE_PAGE_SIZE,
                "platformIdList": [],
                "communityIpIdList": [],
                "isAllPlatform": None,
                "isAllCommunityIp": None,
                "minPrice": None,
                "maxPrice": None,
                "beginTime": None,
                "endTime": None,
                "searchName": "",
                "planeCode": None,
                "topCode": top_code,
            },
        )
        if not arch_data:
            await _log(f"[{top_name}] 热门藏品请求失败，跳过")
            continue

        arch_records = (arch_data.get("data") or {}).get("records") or []
        rows = []
        for rank, item in enumerate(arch_records, start=1):
            rows.append(
                MarketArchiveSnapshot(
                    stat_date=stat_date,
                    top_code=top_code,
                    top_name=top_name,
                    rank=rank,
                    archive_id=item.get("archiveId"),
                    archive_name=item.get("archiveName"),
                    archive_img=item.get("archiveImg"),
                    selling_count=item.get("sellingCount"),
                    deal_count=item.get("dealCount"),
                    market_amount=item.get("marketAmount"),
                    market_amount_rate=item.get("marketAmountRate"),
                    min_amount=item.get("minAmount"),
                    min_amount_rate=item.get("minAmountRate"),
                    avg_amount=item.get("avgAmount"),
                    avg_amount_rate=item.get("avgAmountRate"),
                    up_rate=item.get("upRate"),
                    deal_amount=item.get("dealAmount"),
                    deal_amount_rate=item.get("dealAmountRate"),
                    publish_count=item.get("publishCount"),
                    platform_id=item.get("platformId"),
                    is_transfer=item.get("isTransfer"),
                )
            )

        db.add_all(rows)
        await db.commit()
        total += len(rows)
        await _log(f"[{top_name}] 写入 {len(rows)} 条")

    await _log(f"藏品快照写入完成: 共 {total} 条")
    return total


async def crawl_plane_census(
    db: AsyncSession,
    stat_date: date,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> int:
    """为每个板块调用 censusPlaneArchive，保存涨跌分布到 market_plane_census"""

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    # 先获取板块列表（复用 listNew 接口）
    plane_data = await crawler_client.post_safe("/h5/plane/listNew", {"type": 0, "pageNum": 1, "pageSize": 100})
    if not plane_data:
        await _log("板块列表请求失败，跳过板块成交详细统计")
        return 0

    planes = plane_data.get("data") or []
    total = 0
    for plane in planes:
        plane_code = str(plane.get("code", ""))
        plane_name = str(plane.get("name", ""))
        if not plane_code:
            continue

        census = await crawler_client.post_safe(
            "/h5/market/censusPlaneArchive",
            {"timeType": 0, "planeCode": plane_code},
        )
        if not census:
            await _log(f"[{plane_name}] 板块成交详细请求失败，跳过")
            continue

        d = census.get("data") or {}
        row = MarketPlaneCensus(
            stat_date=stat_date,
            plane_code=plane_code,
            plane_name=plane_name,
            total_market_amount=d.get("totalMarketAmount"),
            total_market_amount_rate=d.get("totalMarketAmountRate"),
            total_deal_count=d.get("totalDealCount"),
            total_deal_count_rate=d.get("totalDealCountRate"),
            total_archive_count=d.get("totalArchiveCount"),
            up_archive_count=d.get("upArchiveCount"),
            down_archive_count=d.get("downArchiveCount"),
            up_down_json=json.dumps(d.get("upDownList") or [], ensure_ascii=False),
        )
        db.add(row)
        total += 1

    await db.commit()
    await _log(f"板块成交详细统计写入完成: {total} 个板块")
    return total


async def crawl_top_census(
    db: AsyncSession,
    stat_date: date,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> int:
    """为每个行情分类调用 censusArchiveTop，保存涨跌分布到 market_top_census"""

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    cat_data = await crawler_client.post_safe("/h5/market/topList", {})
    if not cat_data:
        await _log("行情分类列表请求失败，跳过分类成交详细统计")
        return 0

    categories = (cat_data.get("data") or [])[:_TOP_LIST_MAX_CATEGORIES]
    total = 0
    for cat in categories:
        top_code = str(cat.get("code", ""))
        top_name = str(cat.get("name", ""))
        if not top_code:
            continue

        census = await crawler_client.post_safe(
            "/h5/market/censusArchiveTop",
            {"timeType": 0, "topCode": top_code},
        )
        if not census:
            await _log(f"[{top_name}] 分类成交详细请求失败，跳过")
            continue

        d = census.get("data") or {}
        row = MarketTopCensus(
            stat_date=stat_date,
            top_code=top_code,
            top_name=top_name,
            total_market_amount=d.get("totalMarketAmount"),
            total_market_amount_rate=d.get("totalMarketAmountRate"),
            total_deal_count=d.get("totalDealCount"),
            total_deal_count_rate=d.get("totalDealCountRate"),
            total_archive_count=d.get("totalArchiveCount"),
            up_archive_count=d.get("upArchiveCount"),
            down_archive_count=d.get("downArchiveCount"),
            up_down_json=json.dumps(d.get("upDownList") or [], ensure_ascii=False),
        )
        db.add(row)
        total += 1

    await db.commit()
    await _log(f"行情分类成交详细统计写入完成: {total} 个分类")
    return total


async def build_daily_summary(
    db: AsyncSession,
    stat_date: date,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> None:
    """从当天板块/IP快照中聚合生成 market_daily_summaries"""

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    plane_rows = (
        await db.execute(
            select(MarketPlaneSnapshot).where(MarketPlaneSnapshot.stat_date == stat_date)
        )
    ).scalars().all()

    ip_rows = (
        await db.execute(
            select(MarketIPSnapshot)
            .where(MarketIPSnapshot.stat_date == stat_date)
            .order_by(MarketIPSnapshot.deal_count.desc().nullslast())
        )
    ).scalars().all()

    total_deal_count = sum((r.deal_count or 0) for r in plane_rows)
    total_market_value = sum((r.total_market_value or 0) for r in plane_rows)
    total_deal_amount = sum((r.deal_price or 0) * (r.deal_count or 0) for r in plane_rows)
    active_plane_count = sum(1 for r in plane_rows if (r.deal_count or 0) > 0)

    top_plane = max(plane_rows, key=lambda r: r.deal_count or 0, default=None)
    top_ip = ip_rows[0] if ip_rows else None

    existing = await db.get(MarketDailySummary, stat_date)
    if existing:
        summary = existing
    else:
        summary = MarketDailySummary(stat_date=stat_date)
        db.add(summary)

    summary.total_deal_count = total_deal_count
    summary.total_market_value = total_market_value
    summary.total_deal_amount = total_deal_amount
    summary.active_plane_count = active_plane_count
    summary.top_plane_name = top_plane.plane_name if top_plane else None
    summary.top_plane_deal_count = top_plane.deal_count if top_plane else None
    summary.top_ip_name = top_ip.name if top_ip else None
    summary.top_ip_deal_count = top_ip.deal_count if top_ip else None
    summary.updated_at = datetime.utcnow()

    await db.commit()
    await _log(
        f"每日汇总写入完成: 总成交 {total_deal_count} 笔, 总市值 {total_market_value:.0f}"
    )


async def _clear_existing_snapshots(
    db: AsyncSession,
    stat_date: date,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> None:
    """检查并清除指定日期的全部快照数据（四张表），为重新抓取做准备"""

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    # 各表计数
    plane_cnt = (await db.execute(
        select(func.count()).where(MarketPlaneSnapshot.stat_date == stat_date)
        .select_from(MarketPlaneSnapshot)
    )).scalar() or 0
    ip_cnt = (await db.execute(
        select(func.count()).where(MarketIPSnapshot.stat_date == stat_date)
        .select_from(MarketIPSnapshot)
    )).scalar() or 0
    arch_cnt = (await db.execute(
        select(func.count()).where(MarketArchiveSnapshot.stat_date == stat_date)
        .select_from(MarketArchiveSnapshot)
    )).scalar() or 0
    plane_census_cnt = (await db.execute(
        select(func.count()).where(MarketPlaneCensus.stat_date == stat_date)
        .select_from(MarketPlaneCensus)
    )).scalar() or 0
    top_census_cnt = (await db.execute(
        select(func.count()).where(MarketTopCensus.stat_date == stat_date)
        .select_from(MarketTopCensus)
    )).scalar() or 0
    summary_exists = await db.get(MarketDailySummary, stat_date)

    has_data = (
        plane_cnt > 0 or ip_cnt > 0 or arch_cnt > 0
        or plane_census_cnt > 0 or top_census_cnt > 0
        or summary_exists is not None
    )
    if not has_data:
        await _log(f"[{stat_date}] 无历史数据，直接开始抓取")
        return

    await _log(
        f"[{stat_date}] 发现已有数据 — 板块={plane_cnt} IP={ip_cnt} "
        f"藏品={arch_cnt} 板块普查={plane_census_cnt} 分类普查={top_census_cnt} "
        f"汇总={'有' if summary_exists else '无'}，先清除"
    )

    await db.execute(delete(MarketPlaneSnapshot).where(MarketPlaneSnapshot.stat_date == stat_date))
    await db.execute(delete(MarketIPSnapshot).where(MarketIPSnapshot.stat_date == stat_date))
    await db.execute(delete(MarketArchiveSnapshot).where(MarketArchiveSnapshot.stat_date == stat_date))
    await db.execute(delete(MarketPlaneCensus).where(MarketPlaneCensus.stat_date == stat_date))
    await db.execute(delete(MarketTopCensus).where(MarketTopCensus.stat_date == stat_date))
    if summary_exists:
        await db.delete(summary_exists)
    await db.commit()

    await _log(f"[{stat_date}] 历史数据清除完毕")


async def run_market_snapshot(
    db: AsyncSession,
    stat_date: Optional[date] = None,
    on_log: Optional[Callable[[str], Awaitable[None]]] = None,
) -> dict:
    """执行完整的市场快照流程，返回各步骤写入数量"""
    if stat_date is None:
        stat_date = datetime.utcnow().date()

    async def _log(msg: str):
        logger.info(msg)
        if on_log:
            await on_log(msg)

    await _log(f"开始市场快照抓取: {stat_date}")

    # 先检查并清除当日已有数据
    await _clear_existing_snapshots(db, stat_date, on_log=on_log)

    plane_count = await crawl_plane_snapshots(db, stat_date, on_log=on_log)
    ip_count = await crawl_ip_snapshots(db, stat_date, on_log=on_log)
    archive_count = await crawl_archive_snapshots(db, stat_date, on_log=on_log)
    plane_census_count = await crawl_plane_census(db, stat_date, on_log=on_log)
    top_census_count = await crawl_top_census(db, stat_date, on_log=on_log)
    await build_daily_summary(db, stat_date, on_log=on_log)

    await _log(f"市场快照全部完成: 板块={plane_count} IP={ip_count} 藏品={archive_count} 板块普查={plane_census_count} 分类普查={top_census_count}")
    return {
        "stat_date": str(stat_date),
        "plane_count": plane_count,
        "ip_count": ip_count,
        "archive_count": archive_count,
        "plane_census_count": plane_census_count,
        "top_census_count": top_census_count,
    }
