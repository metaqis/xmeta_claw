"""日报数据获取 — 五个阶段汇总当日数据，Python 侧预计算关键对比指标。

数据流程：
  阶段1 — 发行基础数据  ： 读取当日发行日历，汇总统计量（发行数/总量/总价值等）
  阶段2 — 历史对比数据  ： 查询昨日/上周同日发行数，预计算日环比/周环比变化率
  阶段3 — 丰富发行数据  ：
    3a. DB 含品增强（LaunchDetail + JingtanSkuHomepageDetail）
    3b. 实时 API — h5/goods/archiveGoods 取每个含品的live_total/live_min_price
    3c. IP 深度画像（历史发行次数/粉丝）
    3d. IP 上次发行记录（上次发行时间/作品）
    3e. IP 昨日市场快照（MarketIPSnapshot：成交量/市值）
    3f. 发行主体旗下所有 IP/author 列表
  阶段4 — 行情快照数据  ： 近7天全市场汇总 + 昨日板块/热门藏品/IP快照
"""
import asyncio
from datetime import datetime, timedelta, date as date_type
from typing import Any

from loguru import logger
from sqlalchemy import select, func, and_, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    LaunchCalendar, IP,
    MarketDailySummary, MarketPlaneSnapshot, MarketPlaneCensus,
    MarketTopCensus, MarketArchiveSnapshot, MarketIPSnapshot,
)
from app.article.queries import (
    get_launch_rows,
    summarize_launches,

    enrich_daily_launches,
    get_ip_deep_analysis,
    get_owner_sku_counts,
    get_owner_portfolios,
    get_owner_other_ips,
)


# ─────────────────────────────────────────────────────────────────────────────
# 模块级辅助函数（不依赖 db/外部状态，便于独立测试）
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_archives_live_market(
    archive_pairs: list[tuple[str, str]]
) -> dict[str, dict]:
    """
    并发调用 h5/goods/archiveGoods 接口，获取每个含品的实时在售情况。

    参数：
      archive_pairs — [(archive_id, platform_id), ...] 列表

    返回：
      {archive_id: {"live_total": 在售总挂单数, "live_min_price": 当前地板价}}

    接口说明：
      sellStatus=2 = 在售；pageSize=1 只取摘要（我们只需 total 和 goodsMinPrice）
      total      = 当前在售挂单总数（即预售总量）
      goodsMinPrice = 当前地板价（最低挂单价）
    """
    from app.crawler.client import crawler_client  # 延迟导入避免循环

    result: dict[str, dict] = {}
    sem = asyncio.Semaphore(5)  # 限制对实时 API 的并发，避免被限流

    async def _one(archive_id: str, platform_id: str) -> None:
        async with sem:
            try:
                resp = await crawler_client.post_safe(
                    "/h5/goods/archiveGoods",
                    {
                        "archiveId": archive_id,
                        "platformId": platform_id,
                        "active": "0",
                        "page": 1,
                        "pageSize": 1,
                        "sellStatus": 2,
                        "dealType": "",
                        "goodsType": "",
                        "isPayBond": "",
                        "startTime": "",
                        "endTime": "",
                        "fancyNumberType": "",
                        "goodsNo": None,
                        "sortType": None,
                        "maxPrize": None,
                        "minPrize": None,
                        "isDesignatedNumber": None,
                    },
                )
            except Exception as e:
                logger.warning(f"archiveGoods 调用异常 archiveId={archive_id}: {e}")
                return
            if resp and resp.get("code") == 200:
                data = resp.get("data") or {}
                result[archive_id] = {
                    "live_total": data.get("total") or 0,
                    "live_min_price": data.get("goodsMinPrice"),
                }
            else:
                logger.debug(f"archiveGoods 无数据: archiveId={archive_id}")

    await asyncio.gather(*[_one(aid, pid) for aid, pid in archive_pairs])
    return result


async def _fetch_ip_market_snapshots(
    db: AsyncSession,
    ip_names: list[str],
    yesterday: date_type,
    seven_ago: date_type,
) -> dict[str, dict]:
    """
    查询昨日 + 近7天的 IP 市场快照（来自 MarketIPSnapshot 表）。

    用于：
      - 获取各 IP 昨日的成交量、市值、均价等指标
      - 生成近7天 IP 成交趋势

    返回：
      {ip_name: {"yesterday": {...} | None, "trend_7d": [...]}}
    """
    if not ip_names:
        return {}

    rows = (await db.execute(
        select(MarketIPSnapshot)
        .where(
            and_(
                MarketIPSnapshot.name.in_(ip_names),
                MarketIPSnapshot.stat_date >= seven_ago,
                MarketIPSnapshot.stat_date <= yesterday,
            )
        )
        .order_by(MarketIPSnapshot.name, MarketIPSnapshot.stat_date)
    )).scalars().all()

    result: dict[str, dict] = {}
    for r in rows:
        if r.name not in result:
            result[r.name] = {"yesterday": None, "trend_7d": []}
        entry = {
            "stat_date": str(r.stat_date),
            "deal_count": r.deal_count,
            "deal_count_rate": r.deal_count_rate,   # 成交量日变化 %
            "market_amount": r.market_amount,        # 总市值
            "market_amount_rate": r.market_amount_rate,  # 市值日变化 %
            "avg_amount": r.avg_amount,              # 均价
            "avg_amount_rate": r.avg_amount_rate,    # 均价日变化 %
            "rank": r.rank,
        }
        result[r.name]["trend_7d"].append(entry)
        if str(r.stat_date) == str(yesterday):
            result[r.name]["yesterday"] = entry

    return result


async def _fetch_ip_last_launches(
    db: AsyncSession, ip_names: list[str], before_date: datetime
) -> dict[str, dict]:
    """
    查询每个 IP 在 before_date 之前最近一次的发行记录。

    一次拉取所有候选行（按 IP+时间倒序），Python 侧首次出现即为各 IP 最新一条，
    避免对每个 IP 单独查询。
    """
    target = ip_names[:8] if ip_names else []
    if not target:
        return {}
    rows = (await db.execute(
        select(LaunchCalendar, IP.ip_name)
        .join(IP, LaunchCalendar.ip_id == IP.id)
        .where(
            and_(
                IP.ip_name.in_(target),
                LaunchCalendar.platform_id == 741,
                LaunchCalendar.sell_time < before_date,
            )
        )
        .order_by(IP.ip_name, desc(LaunchCalendar.sell_time))
    )).all()

    result: dict[str, dict] = {}
    for lc, ipn in rows:
        if ipn in result:
            continue  # 已取过该 IP 的最新一条
        result[ipn] = {
            "name": lc.name,
            "sell_time": lc.sell_time.strftime("%Y-%m-%d") if lc.sell_time else "",
            "price": lc.price or 0,
            "count": lc.count or 0,
        }
    return result



async def get_daily_data(db: AsyncSession, target_date: str) -> dict[str, Any]:
    """
    日报核心数据汇总入口，返回供 prompt 使用的完整 dict。

    返回字段说明：
      date                    — 目标日期 YYYY-MM-DD
      launches                — 发行项列表（含 platform_id / ip_name / price / count 等）
      total_launches / total_supply / total_value / avg_price
      ip_distribution         — IP 发行分布（按发行次数降序）
      enriched_launches       — 含品增强列表（含品的 live_total/live_min_price 为实时API值）
      ip_deep_analysis        — IP → {total_launches, recent_1y_launches, fans_count,
                                       description, owners, last_launch, market_snapshot}
      market_analysis         — 行情快照（见 get_market_snapshot_data）
      market_deal_change_pct  — 市场成交量日环比 %（Python预计算）
    """
    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    # ── 阶段1：发行基础数据 ───────────────────────────────────────────────────
    rows = await get_launch_rows(db, date_obj, next_day)
    summary = summarize_launches(rows)

    yesterday = date_obj - timedelta(days=1)

    # ── 阶段2b：近7天每日发行量（用于发行规模横向对比，避免LLM主观臆断）──────
    recent_launch_counts: list[dict] = []
    for i in range(1, 8):
        d = date_obj - timedelta(days=i)
        d_rows = await get_launch_rows(db, d, d + timedelta(days=1))
        d_sum = summarize_launches(d_rows)
        recent_launch_counts.append({
            "date": d.strftime("%Y-%m-%d"),
            "total_launches": d_sum["total_launches"],
            "total_supply": d_sum["total_supply"],
            "total_value": round(d_sum["total_value"], 0),
        })
    recent_launch_counts.reverse()  # 按日期升序

    ip_names = list({l["ip_name"] for l in summary["launches"] if l["ip_name"] != "未知"})

    # ── 阶段3：发行数据增强 ──────────────────────────────────────────────────

    # 3a. DB 含品增强（LaunchDetail + JingtanSkuHomepageDetail 元数据）
    enriched_launches = await enrich_daily_launches(db, summary["launches"])

    # 3b. 实时 API：为每个含品获取 live_total（在售总量）和 live_min_price（地板价）
    #     来源：h5/goods/archiveGoods（见 api_example/16_archive_goods_market.http）
    archive_pairs: list[tuple[str, str]] = []
    for el in enriched_launches:
        pid = str(el.get("platform_id") or 741)
        for ca in el.get("contain_archives") or []:
            aid = ca.get("archive_id") or ""
            if aid:
                archive_pairs.append((aid, pid))

    if archive_pairs:
        live_market = await _fetch_archives_live_market(archive_pairs)
        for el in enriched_launches:
            for ca in el.get("contain_archives") or []:
                aid = ca.get("archive_id") or ""
                if aid and aid in live_market:
                    ca["live_total"] = live_market[aid]["live_total"]
                    ca["live_min_price"] = live_market[aid]["live_min_price"]

    # 3c. IP 深度画像
    ip_deep = await get_ip_deep_analysis(db, ip_names, date_obj)

    # 3d. 聚合今日发行主体信息并注入 ip_deep
    all_owners_today: list[str] = []
    ip_owners_map: dict[str, list[str]] = {}
    for el in enriched_launches:
        ipn = el.get("ip_name") or "未知"
        for ca in el.get("contain_archives") or []:
            owner = ca.get("owner") or ""
            if owner:
                if owner not in all_owners_today:
                    all_owners_today.append(owner)
                ip_owners_map.setdefault(ipn, [])
                if owner not in ip_owners_map[ipn]:
                    ip_owners_map[ipn].append(owner)

    owner_total_counts = await get_owner_sku_counts(db, all_owners_today)
    owner_recent = await get_owner_portfolios(db, all_owners_today, limit=4)
    owner_other_ips = await get_owner_other_ips(db, all_owners_today)

    for ipn, owners in ip_owners_map.items():
        if ipn not in ip_deep:
            ip_deep[ipn] = {
                "total_launches": 0, "recent_1y_launches": 0,
                "fans_count": 0, "description": "", "recent_archives": [],
            }
        ip_deep[ipn]["owners"] = [
            {
                "name": o,
                "total_sku_count": owner_total_counts.get(o, 0),
                "recent_works": [w["name"] for w in owner_recent.get(o, [])[:4]],
                "other_ips": owner_other_ips.get(o, []),  # 该发行主体合作过的所有 IP/author
            }
            for o in owners
        ]

    # 3e. IP 上次发行记录（在今日之前最近一次）
    ip_last_launches = await _fetch_ip_last_launches(db, ip_names, date_obj)
    for ipn, last in ip_last_launches.items():
        if ipn in ip_deep:
            ip_deep[ipn]["last_launch"] = last

    # 3f. IP 昨日市场快照 + 近7天趋势（MarketIPSnapshot 表）
    seven_ago_date = (date_obj - timedelta(days=7)).date()
    yesterday_date = yesterday.date() if hasattr(yesterday, 'date') else yesterday
    ip_market_snapshots = await _fetch_ip_market_snapshots(
        db, ip_names,
        yesterday=yesterday_date,
        seven_ago=seven_ago_date,
    )
    for ipn, snap_data in ip_market_snapshots.items():
        if ipn in ip_deep:
            ip_deep[ipn]["market_snapshot"] = snap_data  # {"yesterday": {...}, "trend_7d": [...]}

    # ── 阶段4：行情快照数据 ──────────────────────────────────────────────────
    market_data = await get_market_snapshot_data(db, date_obj)

    yd_market = (market_data.get("yesterday") or {}) if market_data.get("has_data") else {}
    db_market = (market_data.get("day_before") or {}) if market_data.get("has_data") else {}
    market_deal_change_pct: float | None = None
    if (
        yd_market.get("total_deal_count")
        and db_market.get("total_deal_count")
        and db_market["total_deal_count"] > 0
    ):
        market_deal_change_pct = round(
            (yd_market["total_deal_count"] - db_market["total_deal_count"])
            / db_market["total_deal_count"] * 100,
            1,
        )

    return {
        "date": target_date,
        **summary,
        "recent_launch_counts": recent_launch_counts,
        "enriched_launches": enriched_launches,
        "ip_deep_analysis": ip_deep,
        "market_analysis": market_data,
        "market_deal_change_pct": market_deal_change_pct,
    }


async def get_market_snapshot_data(db: AsyncSession, target_date: datetime) -> dict[str, Any]:
    """
    查询行情快照数据，返回结构化摘要。

    参数：
      target_date — 日报目标日期（今日），行情取 target_date-1（昨日）

    字段说明：
      MarketPlaneSnapshot.avg_price  — 均价「日涨跌幅 %」，不是实际均价
      MarketArchiveSnapshot.avg_amount_rate — 均价日涨跌幅 %
      MarketArchiveSnapshot.avg_amount      — 均价（实际价格）

    返回新增字段（vs 旧版）：
      summaries_7d  — 近7天全市场汇总列表（用于 chart_market_trend_line）
      hot_archives_top10 — 昨日按成交量全局 Top10 藏品（不按分类分组）
    """
    yesterday: date_type = (target_date - timedelta(days=1)).date()
    day_before: date_type = (target_date - timedelta(days=2)).date()

    # ── 近7天全市场汇总 ───────────────────────────────────────────────────────
    seven_days_ago: date_type = (target_date - timedelta(days=7)).date()
    summary_rows = (await db.execute(
        select(MarketDailySummary)
        .where(
            and_(
                MarketDailySummary.stat_date >= seven_days_ago,
                MarketDailySummary.stat_date <= yesterday,
            )
        )
        .order_by(MarketDailySummary.stat_date)
    )).scalars().all()

    summaries_7d: list[dict] = [
        {
            "stat_date": str(r.stat_date),
            "total_deal_count": r.total_deal_count,
            "total_deal_amount": r.total_deal_amount,
            "total_market_value": r.total_market_value,
            "active_plane_count": r.active_plane_count,
            "top_ip_name": r.top_ip_name,
        }
        for r in summary_rows
    ]

    # ── 近7天核心板块总市值（鲸探50 / 禁出文物）──────────────────────────────
    core_dates: list[date_type] = [
        (seven_days_ago + timedelta(days=i)) for i in range(0, 7)
    ]
    core_plane_rows = (await db.execute(
        select(MarketPlaneSnapshot)
        .where(
            and_(
                MarketPlaneSnapshot.stat_date >= seven_days_ago,
                MarketPlaneSnapshot.stat_date <= yesterday,
                or_(
                    MarketPlaneSnapshot.plane_name.in_(["鲸探50", "鲸探 50", "禁出文物", "禁出195", "禁出 195"]),
                    MarketPlaneSnapshot.plane_name.like("%鲸探50%"),
                    MarketPlaneSnapshot.plane_name.like("%禁出%"),
                ),
            )
        )
        .order_by(MarketPlaneSnapshot.stat_date, MarketPlaneSnapshot.plane_name)
    )).scalars().all()

    core_value_map: dict[date_type, dict[str, float | None]] = {
        d: {"jingtan50": None, "restricted_relics": None} for d in core_dates
    }
    for r in core_plane_rows:
        name = (r.plane_name or "").replace(" ", "")
        if "鲸探50" in name:
            old = core_value_map[r.stat_date]["jingtan50"]
            cur = float(r.total_market_value or 0)
            core_value_map[r.stat_date]["jingtan50"] = cur if old is None else max(old, cur)
        elif ("禁出文物" in name) or ("禁出195" in name) or ("禁出" in name):
            old = core_value_map[r.stat_date]["restricted_relics"]
            cur = float(r.total_market_value or 0)
            core_value_map[r.stat_date]["restricted_relics"] = cur if old is None else max(old, cur)

    core_plane_market_values_7d: list[dict] = [
        {
            "stat_date": str(d),
            "jingtan50_market_value": core_value_map[d]["jingtan50"],
            "restricted_relics_market_value": core_value_map[d]["restricted_relics"],
        }
        for d in core_dates
    ]

    def _row_to_summary(r) -> dict:
        return {
            "stat_date": str(r.stat_date),
            "total_deal_count": r.total_deal_count,
            "total_deal_amount": r.total_deal_amount,
            "total_market_value": r.total_market_value,
            "active_plane_count": r.active_plane_count,
            "top_plane_name": r.top_plane_name,
            "top_plane_deal_count": r.top_plane_deal_count,
            "top_ip_name": r.top_ip_name,
            "top_ip_deal_count": r.top_ip_deal_count,
        }

    yesterday_row = (await db.execute(
        select(MarketDailySummary).where(MarketDailySummary.stat_date == yesterday)
    )).scalar_one_or_none()
    day_before_row = (await db.execute(
        select(MarketDailySummary).where(MarketDailySummary.stat_date == day_before)
    )).scalar_one_or_none()

    yesterday_summary = _row_to_summary(yesterday_row) if yesterday_row else None
    day_before_summary = _row_to_summary(day_before_row) if day_before_row else None

    # ── 昨日 Top8 板块快照（按成交量） ─────────────────────────────────────
    top_plane_rows = (await db.execute(
        select(MarketPlaneSnapshot)
        .where(MarketPlaneSnapshot.stat_date == yesterday)
        .order_by(desc(MarketPlaneSnapshot.deal_count))
        .limit(8)
    )).scalars().all()
    top_planes = [
        {
            "plane_name": r.plane_name,
            "deal_count": r.deal_count,
            "deal_price": r.deal_price,
            "avg_price_rate": r.avg_price,   # 均价日涨跌幅 %（非实际均价）
            "total_market_value": r.total_market_value,
            "shelves_rate": r.shelves_rate,
        }
        for r in top_plane_rows
    ]

    # ── 昨日板块涨跌分布（Top10 成交板块） ───────────────────────────────────
    plane_census_rows = (await db.execute(
        select(MarketPlaneCensus)
        .where(MarketPlaneCensus.stat_date == yesterday)
        .order_by(desc(MarketPlaneCensus.total_deal_count))
        .limit(10)
    )).scalars().all()
    plane_census = [
        {
            "plane_name": r.plane_name,
            "total_deal_count": r.total_deal_count,
            "total_deal_count_rate": r.total_deal_count_rate,
            "total_market_amount": r.total_market_amount,
            "total_market_amount_rate": r.total_market_amount_rate,
            "up_archive_count": r.up_archive_count,
            "down_archive_count": r.down_archive_count,
            "total_archive_count": r.total_archive_count,
        }
        for r in plane_census_rows
    ]

    # ── 行情分类成交统计 ───────────────────────────────────────────────────────
    top_census_rows = (await db.execute(
        select(MarketTopCensus)
        .where(MarketTopCensus.stat_date == yesterday)
        .order_by(desc(MarketTopCensus.total_deal_count))
    )).scalars().all()
    top_census = [
        {
            "top_name": r.top_name,
            "total_deal_count": r.total_deal_count,
            "total_deal_count_rate": r.total_deal_count_rate,
            "total_market_amount": r.total_market_amount,
            "total_market_amount_rate": r.total_market_amount_rate,
            "up_archive_count": r.up_archive_count,
            "down_archive_count": r.down_archive_count,
            "total_archive_count": r.total_archive_count,
        }
        for r in top_census_rows
    ]

    # ── 分类 Top5 藏品（用于图表，按分类分组） ──────────────────────────────
    top_archive_rows = (await db.execute(
        select(MarketArchiveSnapshot)
        .where(
            and_(
                MarketArchiveSnapshot.stat_date == yesterday,
                MarketArchiveSnapshot.rank <= 5,
            )
        )
        .order_by(MarketArchiveSnapshot.top_name, MarketArchiveSnapshot.rank)
    )).scalars().all()
    top_archives = [
        {
            "top_name": r.top_name,
            "rank": r.rank,
            "archive_name": r.archive_name,
            "deal_count": r.deal_count,
            "avg_amount": r.avg_amount,
            "avg_amount_rate": r.avg_amount_rate,
            "min_amount": r.min_amount,
            "market_amount": r.market_amount,
            "market_amount_rate": r.market_amount_rate,
            "deal_amount": r.deal_amount,
        }
        for r in top_archive_rows
    ]

    # ── 全局 Top10 热门藏品（按昨日成交量，不分类，用于文章分析） ─────────────
    hot_top10_rows = (await db.execute(
        select(MarketArchiveSnapshot)
        .where(MarketArchiveSnapshot.stat_date == yesterday)
        .order_by(desc(MarketArchiveSnapshot.deal_count))
        .limit(10)
    )).scalars().all()
    hot_archives_top10 = [
        {
            "top_name": r.top_name,
            "rank": r.rank,
            "archive_name": r.archive_name,
            "deal_count": r.deal_count,
            "avg_amount": r.avg_amount,
            "avg_amount_rate": r.avg_amount_rate,
            "min_amount": r.min_amount,
            "market_amount": r.market_amount,
            "deal_amount": r.deal_amount,
        }
        for r in hot_top10_rows
    ]

    # ── 全局昨日成交量 Top5 IP（与今日是否发行无关，用于「热门IP成交Top5」分析） ──
    hot_ip_rows = (await db.execute(
        select(MarketIPSnapshot)
        .where(MarketIPSnapshot.stat_date == yesterday)
        .order_by(desc(MarketIPSnapshot.deal_count))
        .limit(5)
    )).scalars().all()
    hot_ips_top5 = [
        {
            "rank": i + 1,
            "ip_name": r.name,
            "deal_count": r.deal_count or 0,
            "deal_count_rate": r.deal_count_rate,
            "market_amount": r.market_amount,
            "market_amount_rate": r.market_amount_rate,
            "avg_amount": r.avg_amount,
            "avg_amount_rate": r.avg_amount_rate,
        }
        for i, r in enumerate(hot_ip_rows)
    ]

    return {
        "has_data": yesterday_summary is not None,
        "yesterday": yesterday_summary,
        "day_before": day_before_summary,
        "summaries_7d": summaries_7d,           # 近7天全市场汇总（用于折线图）
        "core_plane_market_values_7d": core_plane_market_values_7d,  # 核心板块近7天总市值
        "top_planes": top_planes,
        "plane_census": plane_census,
        "top_census": top_census,
        "top_archives": top_archives,           # 分类 Top5（用于图表）
        "hot_archives_top10": hot_archives_top10,  # 全局 Top10（用于文章分析）
        "hot_ips_top5": hot_ips_top5,           # 全局昨日成交量 Top5 IP
    }

