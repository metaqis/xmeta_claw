# 市场快照数据清理脚本

## 📋 功能说明

用于清除 `market_snapshot_daily` 关联的 6 个数据表中的数据：

| 表名 | 说明 |
|------|------|
| `market_daily_summaries` | 市场每日全局汇总快照 |
| `market_plane_snapshots` | 板块每日市场快照 |
| `market_ip_snapshots` | IP 方每日市场快照 |
| `market_archive_snapshots` | 热门藏品每日排名快照 |
| `market_plane_census` | 板块每日成交详细统计 |
| `market_top_census` | 行情分类每日成交详细统计 |

## 🚀 使用方法

### 前置要求

1. 在 `backend` 目录下执行
2. 已激活 Python 虚拟环境

```bash
cd /home/metaqis/code/xmeta_claw/backend
source venv/bin/activate
```

### 命令示例

#### 1. 清除指定日期的数据

```bash
# 预览模式（不实际删除）
python scripts/clear_market_snapshots.py --date 2026-04-12 --dry-run

# 实际删除
python scripts/clear_market_snapshots.py --date 2026-04-12
```

#### 2. 清除日期范围的数据

```bash
# 预览模式
python scripts/clear_market_snapshots.py --start 2026-04-01 --end 2026-04-10 --dry-run

# 实际删除
python scripts/clear_market_snapshots.py --start 2026-04-01 --end 2026-04-10
```

#### 3. 清除所有数据

```bash
# 预览模式
python scripts/clear_market_snapshots.py --all --dry-run

# 实际删除（需要输入 YES 确认）
python scripts/clear_market_snapshots.py --all
```

#### 4. 清除 N 天前的数据

```bash
# 预览 30 天前的数据
python scripts/clear_market_snapshots.py --days-ago 30 --dry-run

# 实际删除 30 天前的数据
python scripts/clear_market_snapshots.py --days-ago 30
```

## ⚠️ 注意事项

1. **预览模式**：使用 `--dry-run` 参数可以先查看要删除的数据量，不会实际删除
2. **确认删除**：实际删除时需要输入 `yes` 或 `YES` 确认
3. **事务安全**：所有删除操作在单个事务中执行，要么全部成功，要么全部回滚
4. **数据备份**：建议在执行删除操作前先备份数据库

## 🔧 示例输出

### 预览模式

```
📊 统计 2026-04-12 的数据：
------------------------------------------------------------
  🔴 MarketDailySummary             :      1 条
  🔴 MarketPlaneSnapshot            :     12 条
  🔴 MarketIPSnapshot               :     50 条
  🔴 MarketArchiveSnapshot          :    299 条
  🔴 MarketPlaneCensus              :     12 条
  🔴 MarketTopCensus                :      6 条
------------------------------------------------------------
  总计：380 条记录

⚠️  预览模式（未实际删除）
```

### 实际删除

```
🗑️  开始删除 2026-04-12 的数据：
------------------------------------------------------------
  ✅ MarketDailySummary             :      1 条
  ✅ MarketPlaneSnapshot            :     12 条
  ✅ MarketIPSnapshot               :     50 条
  ✅ MarketArchiveSnapshot          :    299 条
  ✅ MarketPlaneCensus              :     12 条
  ✅ MarketTopCensus                :      6 条
------------------------------------------------------------
✅ 删除完成！
```

## 🛡️ 安全提示

- 删除操作不可恢复，请谨慎操作
- 生产环境执行前建议先在测试环境验证
- 重要数据请先备份再删除
