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
    """每个发行主体（owner）的近期鲸探作品。

    一次查询拉回所有 owner 的最新作品（按 sku_issue_time_ms desc），
    Python 侧分组并截取每个 owner 的前 N 条；避免 N+1 查询。
    """
    target_owners = owners[:6]
    if not target_owners:
        return {}
    # 拉取每个 owner 的多条候选；外层多取一些以便分组截取
    rows = (await db.execute(
        select(JingtanSkuHomepageDetail)
        .where(JingtanSkuHomepageDetail.owner.in_(target_owners))
        .order_by(JingtanSkuHomepageDetail.sku_issue_time_ms.desc())
        .limit(limit * len(target_owners) * 4)  # 留余量保证每个 owner 都能取到 limit 条
    )).scalars().all()

    portfolios: dict[str, list[dict]] = {o: [] for o in target_owners}
    for s in rows:
        bucket = portfolios.get(s.owner)
        if bucket is None or len(bucket) >= limit:
            continue
        bucket.append({
            "sku_id": s.sku_id,
            "name": s.sku_name,
            "author": s.author or "",
            "mini_file_url": s.mini_file_url or "",
            "quantity": s.sku_quantity,
        })
    return portfolios


async def get_author_portfolios(
    db: AsyncSession, authors: list[str], limit: int = 6
) -> dict[str, list[dict]]:
    """每个艺术家/author 的近期鲸探作品（批量查询，Python 侧分组）。"""
    target_authors = authors[:6]
    if not target_authors:
        return {}
    rows = (await db.execute(
        select(JingtanSkuHomepageDetail)
        .where(JingtanSkuHomepageDetail.author.in_(target_authors))
        .order_by(JingtanSkuHomepageDetail.sku_issue_time_ms.desc())
        .limit(limit * len(target_authors) * 4)
    )).scalars().all()

    portfolios: dict[str, list[dict]] = {a: [] for a in target_authors}
    for s in rows:
        bucket = portfolios.get(s.author)
        if bucket is None or len(bucket) >= limit:
            continue
        bucket.append({
            "sku_id": s.sku_id,
            "name": s.sku_name,
            "owner": s.owner or "",
            "mini_file_url": s.mini_file_url or "",
            "quantity": s.sku_quantity,
        })
    return portfolios


async def get_owner_sku_counts(db: AsyncSession, owners: list[str]) -> dict[str, int]:
    """每个发行主体在鲸探上的历史藏品总数量（一次 GROUP BY 完成）。"""
    target_owners = owners[:10]
    if not target_owners:
        return {}
    rows = (await db.execute(
        select(
            JingtanSkuHomepageDetail.owner,
            func.count(JingtanSkuHomepageDetail.sku_id),
        )
        .where(JingtanSkuHomepageDetail.owner.in_(target_owners))
        .group_by(JingtanSkuHomepageDetail.owner)
    )).all()
    counts = {o: 0 for o in target_owners}
    for owner, cnt in rows:
        counts[owner] = cnt or 0
    return counts


async def get_ip_deep_analysis(
    db: AsyncSession,
    ip_names: list[str],
    date_obj,
) -> dict[str, dict]:
    """
    对每个 IP 做深度画像：历史/近一年发行次数、粉丝数、简介。
    owners 字段由调用方（analyzer）注入。

    一次 IN 查询 + GROUP BY 获取 total/recent_1y/IP 元信息，避免 N+1。
    """
    target = ip_names[:8]
    if not target:
        return {}
    one_year_ago = date_obj - timedelta(days=365)

    # 历史总发行次数（按 IP 分组聚合）
    total_rows = (await db.execute(
        select(IP.ip_name, func.count(LaunchCalendar.id))
        .join(LaunchCalendar, LaunchCalendar.ip_id == IP.id)
        .where(
            and_(
                IP.ip_name.in_(target),
                LaunchCalendar.platform_id == 741,
            )
        )
        .group_by(IP.ip_name)
    )).all()
    total_map = {name: cnt or 0 for name, cnt in total_rows}

    # 近一年发行次数
    r1y_rows = (await db.execute(
        select(IP.ip_name, func.count(LaunchCalendar.id))
        .join(LaunchCalendar, LaunchCalendar.ip_id == IP.id)
        .where(
            and_(
                IP.ip_name.in_(target),
                LaunchCalendar.platform_id == 741,
                LaunchCalendar.sell_time >= one_year_ago,
                LaunchCalendar.sell_time < date_obj,
            )
        )
        .group_by(IP.ip_name)
    )).all()
    r1y_map = {name: cnt or 0 for name, cnt in r1y_rows}

    # IP 元信息（粉丝/简介）
    ip_rows = (await db.execute(
        select(IP).where(IP.ip_name.in_(target))
    )).scalars().all()
    ip_meta_map = {ip.ip_name: ip for ip in ip_rows}

    result: dict[str, dict] = {}
    for ipn in target:
        meta = ip_meta_map.get(ipn)
        result[ipn] = {
            "total_launches": total_map.get(ipn, 0),
            "recent_1y_launches": r1y_map.get(ipn, 0),
            "fans_count": (meta.fans_count or 0) if meta else 0,
            "description": (meta.description or "") if meta else "",
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
    """查询每个发行主体（owner）合作过的所有 author（IP方），一次 IN 查询完成。"""
    target = owners[:8]
    if not target:
        return {}
    rows = (await db.execute(
        select(JingtanSkuHomepageDetail.owner, JingtanSkuHomepageDetail.author)
        .where(
            and_(
                JingtanSkuHomepageDetail.owner.in_(target),
                JingtanSkuHomepageDetail.author.isnot(None),
                JingtanSkuHomepageDetail.author != "",
            )
        )
        .distinct()
    )).all()
    result: dict[str, list[str]] = {o: [] for o in target}
    for owner, author in rows:
        if author and author not in result[owner]:
            result[owner].append(author)
    return result
