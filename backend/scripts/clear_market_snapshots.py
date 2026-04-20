#!/usr/bin/env python3
"""
清除市场每日快照关联数据表中的数据

运行前请确保：
1. 在 backend 目录下执行
2. 已激活虚拟环境
3. 设置 PYTHONPATH 或从正确的目录运行

支持多种清除模式：
- 清除指定日期的数据
- 清除指定日期范围的数据
- 清除所有数据
- 清除 N 天前的旧数据

使用方法：
  # 清除指定日期的数据
  python clear_market_snapshots.py --date 2026-04-12
  
  # 清除日期范围的数据
  python clear_market_snapshots.py --start 2026-04-01 --end 2026-04-10
  
  # 清除所有数据
  python clear_market_snapshots.py --all
  
  # 清除 30 天前的数据
  python clear_market_snapshots.py --days-ago 30
  
  # 预览要删除的数据（不实际删除）
  python clear_market_snapshots.py --date 2026-04-12 --dry-run
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select, func
from app.database.db import async_session, engine
from app.database.models import (
    MarketDailySummary,
    MarketPlaneSnapshot,
    MarketIPSnapshot,
    MarketArchiveSnapshot,
    MarketPlaneCensus,
    MarketTopCensus,
)


# 所有市场快照相关表
MARKET_TABLES = [
    ("MarketDailySummary", MarketDailySummary, "stat_date"),
    ("MarketPlaneSnapshot", MarketPlaneSnapshot, "stat_date"),
    ("MarketIPSnapshot", MarketIPSnapshot, "stat_date"),
    ("MarketArchiveSnapshot", MarketArchiveSnapshot, "stat_date"),
    ("MarketPlaneCensus", MarketPlaneCensus, "stat_date"),
    ("MarketTopCensus", MarketTopCensus, "stat_date"),
]


async def count_records(session, model, date_field: str, date_value) -> int:
    """统计符合条件的记录数"""
    stmt = select(func.count()).select_from(model).where(getattr(model, date_field) == date_value)
    result = await session.execute(stmt)
    return result.scalar() or 0


async def delete_records(session, model, date_field: str, date_value) -> int:
    """删除符合条件的记录"""
    stmt = delete(model).where(getattr(model, date_field) == date_value)
    result = await session.execute(stmt)
    return result.rowcount or 0


async def count_records_range(session, model, date_field: str, start_date, end_date) -> int:
    """统计日期范围内的记录数"""
    stmt = select(func.count()).select_from(model).where(
        getattr(model, date_field) >= start_date,
        getattr(model, date_field) <= end_date,
    )
    result = await session.execute(stmt)
    return result.scalar() or 0


async def delete_records_range(session, model, date_field: str, start_date, end_date) -> int:
    """删除日期范围内的记录"""
    stmt = delete(model).where(
        getattr(model, date_field) >= start_date,
        getattr(model, date_field) <= end_date,
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


async def clear_by_date(target_date: str, dry_run: bool = False):
    """清除指定日期的数据"""
    from datetime import date
    
    # 将字符串转换为 date 对象
    target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    
    async with async_session() as db:
        print(f"\n📊 统计 {target_date} 的数据：")
        print("-" * 60)
        
        total_count = 0
        for table_name, model, date_field in MARKET_TABLES:
            count = await count_records(db, model, date_field, target_date_obj)
            total_count += count
            status = "🔴" if count > 0 else "✓"
            print(f"  {status} {table_name:30s} : {count:6,} 条")
        
        print("-" * 60)
        print(f"  总计：{total_count:,} 条记录\n")
        
        if dry_run:
            print("⚠️  预览模式（未实际删除）")
            return
        
        if total_count == 0:
            print("✅ 没有数据需要删除")
            return
        
        # 确认删除
        confirm = input(f"确认删除 {total_count:,} 条记录？(yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ 已取消")
            return
        
        print(f"\n🗑️  开始删除 {target_date} 的数据：")
        print("-" * 60)
        
        for table_name, model, date_field in MARKET_TABLES:
            deleted = await delete_records(db, model, date_field, target_date)
            status = "✅" if deleted > 0 else "  "
            print(f"  {status} {table_name:30s} : {deleted:6,} 条")
        
        await db.commit()
        print("-" * 60)
        print(f"✅ 删除完成！\n")


async def clear_by_date_range(start_date: str, end_date: str, dry_run: bool = False):
    """清除日期范围内的数据"""
    # 将字符串转换为 date 对象
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    async with async_session() as db:
        print(f"\n📊 统计 {start_date} 至 {end_date} 的数据：")
        print("-" * 60)
        
        total_count = 0
        for table_name, model, date_field in MARKET_TABLES:
            count = await count_records_range(db, model, date_field, start_date_obj, end_date_obj)
            total_count += count
            status = "🔴" if count > 0 else "✓"
            print(f"  {status} {table_name:30s} : {count:6,} 条")
        
        print("-" * 60)
        print(f"  总计：{total_count:,} 条记录\n")
        
        if dry_run:
            print("⚠️  预览模式（未实际删除）")
            return
        
        if total_count == 0:
            print("✅ 没有数据需要删除")
            return
        
        # 确认删除
        confirm = input(f"确认删除 {total_count:,} 条记录？(yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ 已取消")
            return
        
        print(f"\n🗑️  开始删除 {start_date} 至 {end_date} 的数据：")
        print("-" * 60)
        
        for table_name, model, date_field in MARKET_TABLES:
            deleted = await delete_records_range(db, model, date_field, start_date, end_date)
            status = "✅" if deleted > 0 else "  "
            print(f"  {status} {table_name:30s} : {deleted:6,} 条")
        
        await db.commit()
        print("-" * 60)
        print(f"✅ 删除完成！\n")


async def clear_all(dry_run: bool = False):
    """清除所有数据"""
    async with async_session() as db:
        print(f"\n📊 统计所有市场快照数据：")
        print("-" * 60)
        
        total_count = 0
        for table_name, model, date_field in MARKET_TABLES:
            count = await count_records(db, model, date_field, None)  # 统计所有
            # 对于全表统计，使用不同的查询
            stmt = select(func.count()).select_from(model)
            result = await db.execute(stmt)
            count = result.scalar() or 0
            
            total_count += count
            status = "🔴" if count > 0 else "✓"
            print(f"  {status} {table_name:30s} : {count:6,} 条")
        
        print("-" * 60)
        print(f"  总计：{total_count:,} 条记录\n")
        
        if dry_run:
            print("⚠️  预览模式（未实际删除）")
            return
        
        if total_count == 0:
            print("✅ 没有数据需要删除")
            return
        
        # 确认删除
        print("⚠️  警告：这将删除所有市场快照数据！")
        confirm = input(f"确认删除所有 {total_count:,} 条记录？(输入 YES 确认): ")
        if confirm != 'YES':
            print("❌ 已取消")
            return
        
        print(f"\n🗑️  开始删除所有数据：")
        print("-" * 60)
        
        for table_name, model, date_field in MARKET_TABLES:
            stmt = delete(model)
            result = await db.execute(stmt)
            deleted = result.rowcount or 0
            status = "✅" if deleted > 0 else "  "
            print(f"  {status} {table_name:30s} : {deleted:6,} 条")
        
        await db.commit()
        print("-" * 60)
        print(f"✅ 删除完成！\n")


async def clear_days_ago(days: int, dry_run: bool = False):
    """清除 N 天前的数据"""
    from sqlalchemy.types import Date
    
    cutoff_date = (datetime.now() - timedelta(days=days)).date()
    
    async with async_session() as db:
        print(f"\n📊 统计 {days} 天前 ({cutoff_date}) 的数据：")
        print("-" * 60)
        
        total_count = 0
        for table_name, model, date_field in MARKET_TABLES:
            stmt = select(func.count()).select_from(model).where(
                getattr(model, date_field) < cutoff_date
            )
            result = await db.execute(stmt)
            count = result.scalar() or 0
            total_count += count
            status = "🔴" if count > 0 else "✓"
            print(f"  {status} {table_name:30s} : {count:6,} 条")
        
        print("-" * 60)
        print(f"  总计：{total_count:,} 条记录\n")
        
        if dry_run:
            print("⚠️  预览模式（未实际删除）")
            return
        
        if total_count == 0:
            print("✅ 没有数据需要删除")
            return
        
        # 确认删除
        confirm = input(f"确认删除 {total_count:,} 条记录？(yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ 已取消")
            return
        
        print(f"\n🗑️  开始删除 {days} 天前的数据：")
        print("-" * 60)
        
        for table_name, model, date_field in MARKET_TABLES:
            stmt = delete(model).where(getattr(model, date_field) < cutoff_date)
            result = await db.execute(stmt)
            deleted = result.rowcount or 0
            status = "✅" if deleted > 0 else "  "
            print(f"  {status} {table_name:30s} : {deleted:6,} 条")
        
        await db.commit()
        print("-" * 60)
        print(f"✅ 删除完成！\n")


def main():
    import asyncio
    
    parser = argparse.ArgumentParser(
        description="清除市场每日快照关联数据表中的数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 清除指定日期的数据
  python clear_market_snapshots.py --date 2026-04-12
  
  # 清除日期范围的数据
  python clear_market_snapshots.py --start 2026-04-01 --end 2026-04-10
  
  # 清除所有数据
  python clear_market_snapshots.py --all
  
  # 清除 30 天前的数据
  python clear_market_snapshots.py --days-ago 30
  
  # 预览模式（不实际删除）
  python clear_market_snapshots.py --date 2026-04-12 --dry-run
        """
    )
    
    parser.add_argument("--date", type=str, help="清除指定日期的数据 (YYYY-MM-DD)")
    parser.add_argument("--start", type=str, help="清除日期范围的开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="清除日期范围的结束日期 (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="清除所有数据")
    parser.add_argument("--days-ago", type=int, help="清除 N 天前的数据")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际删除")
    
    args = parser.parse_args()
    
    # 验证参数
    mode_count = sum([
        bool(args.date),
        bool(args.start and args.end),
        bool(args.all),
        bool(args.days_ago),
    ])
    
    if mode_count == 0:
        parser.print_help()
        print("\n❌ 错误：请指定一种清除模式")
        return
    elif mode_count > 1:
        parser.print_help()
        print("\n❌ 错误：只能指定一种清除模式")
        return
    
    # 执行清除
    if args.date:
        asyncio.run(clear_by_date(args.date, args.dry_run))
    elif args.start and args.end:
        asyncio.run(clear_by_date_range(args.start, args.end, args.dry_run))
    elif args.all:
        asyncio.run(clear_all(args.dry_run))
    elif args.days_ago:
        asyncio.run(clear_days_ago(args.days_ago, args.dry_run))


if __name__ == "__main__":
    main()
