"""市场数据爬虫 - 定时更新价格"""
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.client import crawler_client
from app.database.models import Archive, ArchiveMarket, ArchivePriceHistory


PLATFORM_ID_JINGTAN = "741"


async def update_market_data(db: AsyncSession):
    """更新所有藏品的市场数据"""
    result = await db.execute(select(Archive))
    archives = result.scalars().all()
    logger.info(f"开始更新市场数据: {len(archives)} 个藏品")

    updated = 0
    for archive in archives:
        success = await _update_single_archive_market(db, archive.archive_id)
        if success:
            updated += 1

    await db.commit()
    logger.info(f"市场数据更新完成: {updated}/{len(archives)}")
    return updated


async def _update_single_archive_market(db: AsyncSession, archive_id: str) -> bool:
    """更新单个藏品的市场数据"""
    data = await crawler_client.post_safe(
        "/h5/goods/archive",
        {
            "archiveId": archive_id,
            "platformId": PLATFORM_ID_JINGTAN,
            "page": 1,
            "pageSize": 1,
            "sellStatus": 1,
        },
    )
    if not data:
        return False

    records = data.get("data", {}).get("list", [])
    if not records:
        return False

    item = records[0]
    now = datetime.utcnow()

    goods_min_price = item.get("goodsMinPrice")
    want_buy_count = item.get("wantBuyCount", 0)
    selling_count = item.get("sellingCount", 0)
    deal_count = item.get("dealCount", 0)
    want_buy_max_price = item.get("wantBuyMaxPrice")
    deal_price = item.get("dealPrice")

    # 更新或创建 market 记录
    market_result = await db.execute(
        select(ArchiveMarket).where(ArchiveMarket.archive_id == archive_id)
    )
    market = market_result.scalar_one_or_none()

    if market:
        market.goods_min_price = goods_min_price
        market.want_buy_count = want_buy_count
        market.selling_count = selling_count
        market.deal_count = deal_count
        market.want_buy_max_price = want_buy_max_price
        market.deal_price = deal_price
        market.record_time = now
    else:
        market = ArchiveMarket(
            archive_id=archive_id,
            goods_min_price=goods_min_price,
            want_buy_count=want_buy_count,
            selling_count=selling_count,
            deal_count=deal_count,
            want_buy_max_price=want_buy_max_price,
            deal_price=deal_price,
            record_time=now,
        )
        db.add(market)

    # 记录价格历史
    history = ArchivePriceHistory(
        archive_id=archive_id,
        min_price=goods_min_price,
        sell_count=selling_count,
        buy_count=want_buy_count,
        deal_count=deal_count,
        record_time=now,
    )
    db.add(history)

    return True
