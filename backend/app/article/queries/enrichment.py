"""数据增强查询 — LaunchDetail / JingtanSku / IP画像 / 作品集等。"""
import json
from datetime import timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    LaunchDetail,
    JingtanSkuWiki,
    JingtanSkuHomepageDetail,
    IP,
    LaunchCalendar,
)


async def get_launch_details(db: AsyncSession, launches: list[dict]) -> dict[int, dict]:
    """从 LaunchDetail.raw_json 解析 containArchiveList / associationArchiveList。"""
    launch_ids = [l["launch_id"] for l in launches if l.get("launch_id")]
    if not launch_ids:
        return {}
    result = await db.execute(
        select(LaunchDetail).where(LaunchDetail.launch_id.in_(launch_ids))
    )
    detail_map: dict[int, dict] = {}
    for d in result.scalars().all():
        if not d.raw_json:
            continue
        try:
            raw = json.loads(d.raw_json)
            detail_map[d.launch_id] = {
                "containArchiveList": raw.get("containArchiveList") or [],
                "associationArchiveList": raw.get("associationArchiveList") or [],
            }
        except (json.JSONDecodeError, AttributeError):
            pass
    return detail_map


async def match_jingtan_archives(db: AsyncSession, archive_names: list[str]) -> dict[str, dict]:
    """archive_name → JingtanSkuHomepageDetail（优先），退化到 JingtanSkuWiki。"""
    if not archive_names:
        return {}
    hp_result = await db.execute(
        select(JingtanSkuHomepageDetail).where(
            JingtanSkuHomepageDetail.sku_name.in_(archive_names)
        )
    )
    matched: dict[str, dict] = {}
    for d in hp_result.scalars().all():
        matched[d.sku_name] = {
            "sku_id": d.sku_id,
            "author": d.author or "",
            "owner": d.owner or "",
            "sku_desc": (d.sku_desc or "")[:500],
            "mini_file_url": d.mini_file_url or "",
            "origin_file_url": d.origin_file_url or "",
            "producer_name": d.producer_name or "",
            "sku_quantity": d.sku_quantity,
            "sku_issue_time_ms": d.sku_issue_time_ms,
        }
    remaining = [n for n in archive_names if n not in matched]
    if remaining:
        wiki_result = await db.execute(
            select(JingtanSkuWiki).where(JingtanSkuWiki.sku_name.in_(remaining))
        )
        for w in wiki_result.scalars().all():
            matched[w.sku_name] = {
                "sku_id": w.sku_id,
                "author": w.author or "",
                "owner": w.owner or "",
                "sku_desc": "",
                "mini_file_url": w.mini_file_url or "",
                "origin_file_url": "",
                "producer_name": "",
                "sku_quantity": w.sku_quantity,
                "sku_issue_time_ms": w.sku_issue_time_ms,
            }
    return matched


async def get_owner_portfolios(
    db: AsyncSession, owners: list[str], limit: int = 6
) -> dict[str, list[dict]]:
    """每个发行主体（owner）的近期鲸探作品。"""
    portfolios: dict[str, list[dict]] = {}
    for owner in owners[:6]:
        r = await db.execute(
            select(JingtanSkuHomepageDetail)
            .where(JingtanSkuHomepageDetail.owner == owner)
            .order_by(JingtanSkuHomepageDetail.sku_issue_time_ms.desc())
            .limit(limit)
        )
        portfolios[owner] = [
            {
                "sku_id": s.sku_id,
                "name": s.sku_name,
                "author": s.author or "",
                "mini_file_url": s.mini_file_url or "",
                "quantity": s.sku_quantity,
            }
            for s in r.scalars().all()
        ]
    return portfolios


async def get_author_portfolios(
    db: AsyncSession, authors: list[str], limit: int = 6
) -> dict[str, list[dict]]:
    """每个艺术家/author 的近期鲸探作品。"""
    portfolios: dict[str, list[dict]] = {}
    for author in authors[:6]:
        r = await db.execute(
            select(JingtanSkuHomepageDetail)
            .where(JingtanSkuHomepageDetail.author == author)
            .order_by(JingtanSkuHomepageDetail.sku_issue_time_ms.desc())
            .limit(limit)
        )
        portfolios[author] = [
            {
                "sku_id": s.sku_id,
                "name": s.sku_name,
                "owner": s.owner or "",
                "mini_file_url": s.mini_file_url or "",
                "quantity": s.sku_quantity,
            }
            for s in r.scalars().all()
        ]
    return portfolios


async def get_owner_sku_counts(db: AsyncSession, owners: list[str]) -> dict[str, int]:
    """每个发行主体在鲸探上的历史藏品总数量。"""
    counts: dict[str, int] = {}
    for owner in owners[:10]:
        cnt = (
            await db.execute(
                select(func.count(JingtanSkuHomepageDetail.sku_id)).where(
                    JingtanSkuHomepageDetail.owner == owner
                )
            )
        ).scalar() or 0
        counts[owner] = cnt
    return counts


async def get_ip_deep_analysis(
    db: AsyncSession,
    ip_names: list[str],
    date_obj,
) -> dict[str, dict]:
    """
    对每个 IP 做深度画像：历史/近一年发行次数、粉丝数、简介。
    owners 字段由调用方（analyzer）注入。
    """
    one_year_ago = date_obj - timedelta(days=365)
    result: dict[str, dict] = {}

    for ipn in ip_names[:8]:
        total = (
            await db.execute(
                select(func.count(LaunchCalendar.id))
                .join(IP, LaunchCalendar.ip_id == IP.id)
                .where(IP.ip_name == ipn)
                .where(LaunchCalendar.platform_id == 741)
            )
        ).scalar() or 0

        r1y = (
            await db.execute(
                select(func.count(LaunchCalendar.id))
                .join(IP, LaunchCalendar.ip_id == IP.id)
                .where(
                    and_(
                        IP.ip_name == ipn,
                        LaunchCalendar.platform_id == 741,
                        LaunchCalendar.sell_time >= one_year_ago,
                        LaunchCalendar.sell_time < date_obj,
                    )
                )
            )
        ).scalar() or 0

        ip_row = (
            await db.execute(
                select(IP)
                .join(LaunchCalendar, LaunchCalendar.ip_id == IP.id)
                .where(IP.ip_name == ipn)
                .limit(1)
            )
        ).scalars().first()

        result[ipn] = {
            "total_launches": total,
            "recent_1y_launches": r1y,
            "fans_count": (ip_row.fans_count or 0) if ip_row else 0,
            "description": (ip_row.description or "") if ip_row else "",
            "recent_archives": [],
            "owners": [],
        }

    return result


async def enrich_daily_launches(db: AsyncSession, launches: list[dict]) -> list[dict]:
    """为每个发行项补充 contain_archives / association_archives（含市场数据 + 鲸探信息）。"""
    detail_map = await get_launch_details(db, launches)

    all_archive_names: list[str] = []
    for launch in launches:
        detail = detail_map.get(launch.get("launch_id") or 0, {})
        for item in detail.get("containArchiveList", []):
            name = item.get("archiveName") or ""
            if name and name not in all_archive_names:
                all_archive_names.append(name)

    jingtan_map = await match_jingtan_archives(db, all_archive_names)

    all_owners: list[str] = []
    all_authors: list[str] = []
    for jd in jingtan_map.values():
        if jd.get("owner") and jd["owner"] not in all_owners:
            all_owners.append(jd["owner"])
        if jd.get("author") and jd["author"] not in all_authors:
            all_authors.append(jd["author"])

    owner_portfolios = await get_owner_portfolios(db, all_owners)
    author_portfolios = await get_author_portfolios(db, all_authors)

    enriched: list[dict] = []
    for launch in launches:
        launch_id = launch.get("launch_id") or 0
        detail = detail_map.get(launch_id, {})

        contain_archives: list[dict] = []
        for item in detail.get("containArchiveList", []):
            archive_name = item.get("archiveName") or ""
            jd = jingtan_map.get(archive_name, {})
            owner = jd.get("owner") or ""
            author = jd.get("author") or ""
            contain_archives.append({
                "archive_id": str(item.get("associatedArchiveId") or ""),
                "archive_name": archive_name,
                "archive_img": item.get("archiveImg") or "",
                "sales_num": item.get("salesNum") or 0,
                "percentage": item.get("percentage") or 0,
                "selling_count": item.get("sellingCount") or 0,
                "deal_count": item.get("dealCount") or 0,
                "min_price": item.get("goodsMinPrice") or 0,
                "ip_name": item.get("ipName") or "",
                "is_transfer": bool(item.get("isTransfer")),
                "sku_id": jd.get("sku_id") or "",
                "author": author,
                "owner": owner,
                "sku_desc": jd.get("sku_desc") or "",
                "jingtan_img": jd.get("mini_file_url") or "",
                "owner_portfolio": owner_portfolios.get(owner, [])[:5],
                "author_portfolio": author_portfolios.get(author, [])[:5],
            })

        association_archives: list[dict] = []
        for item in detail.get("associationArchiveList", []):
            association_archives.append({
                "archive_id": str(item.get("associatedArchiveId") or ""),
                "archive_name": item.get("archiveName") or "",
                "archive_img": item.get("archiveImg") or "",
                "selling_count": item.get("sellingCount") or 0,
                "deal_count": item.get("dealCount") or 0,
                "min_price": item.get("goodsMinPrice") or 0,
                "is_transfer": bool(item.get("isTransfer")),
            })

        enriched.append({
            **launch,
            "contain_archives": contain_archives,
            "association_archives": association_archives,
        })

    return enriched


async def get_owner_other_ips(
    db: AsyncSession, owners: list[str]
) -> dict[str, list[str]]:
    """查询每个发行主体（owner）合作过的所有 author（IP方），用于分析发行商旗下IP矩阵。"""
    result: dict[str, list[str]] = {}
    for owner in owners[:8]:
        rows = (await db.execute(
            select(JingtanSkuHomepageDetail.author)
            .where(
                and_(
                    JingtanSkuHomepageDetail.owner == owner,
                    JingtanSkuHomepageDetail.author.isnot(None),
                    JingtanSkuHomepageDetail.author != "",
                )
            )
            .distinct()
        )).scalars().all()
        result[owner] = [r for r in rows if r]
    return result
