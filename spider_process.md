# 爬虫流程

## 总体架构

```
┌─────────────────────────────────────────────────────┐
│                    反封策略层                          │
│  UA轮转 · 随机延迟 · Headers变换 · 代理 · 并发控制    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              CrawlerClient (连接池)                    │
│  httpx AsyncClient · 持久连接 · 指数退避重试           │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   第一阶段         第二阶段       定时任务
   日历数据         藏品ID补齐     周期调度
```

## 反封策略

| 策略 | 实现 |
|------|------|
| UA 轮转 | 9 个 User-Agent (Android/iOS/桌面) 每请求随机选取 |
| 随机延迟 | 基础延迟(0.5s) ±40% 抖动：`max(0.1, base + base * uniform(-0.4, 0.4))` |
| Headers 变换 | Accept-Language (4种)、Accept、Cache-Control 随机组合 |
| 连接池 | httpx 持久化连接池 (max=20, keepalive=10)，减少 TCP/TLS 握手 |
| 并发控制 | asyncio.Semaphore 限制最大并发请求数 (默认 3) |
| 代理支持 | 可配置 CRAWLER_PROXY 环境变量，支持 HTTP/SOCKS 代理 |
| 指数退避 | tenacity: 3 次重试，等待 2s→4s→8s（最大 30s） |
| 优雅降级 | `post_safe()` 捕获所有异常返回 None，不中断批量任务 |

## 第一阶段：日历数据提取

### 流程图

```
遍历日期 (today+7 ~ 往前, 连续15天无数据停止)
  │
  ▼
获取日历列表 ────────────────────────────────────────────┐
POST /h5/news/launchCalendar/list                        │
{"pageNum":1, "pageSize":50, "date":"2026-03-13"}        │
  │                                                      │
  ▼                                                      │
遍历每条记录 ──► 查数据库是否已存在(source_id)             │
  │    │                                                  │
  │    └─ 已存在: 补全 platform/ip 关系, 检查详情          │
  │                                                      │
  ▼ 不存在                                               │
写入 launch_calendar 表                                   │
  │                                                      │
  ▼                                                      │
获取发行详情                                              │
POST /h5/news/launchCalendar/detailed {"id": 4692}       │
  │                                                      │
  ▼                                                      │
写入 launch_detail 表 (含 raw_json)                       │
  │                                                      │
  ▼                                                      │
从详情中提取关联藏品                                      │
  containArchiveList[].associatedArchiveId                │
  associationArchiveList[].associatedArchiveId            │
  │                                                      │
  ▼                                                      │
对每个 archive_id:                                        │
  查询 archives 表是否已存在                               │
  │    │                                                  │
  │    └─ 已存在但缺 IP/类型: 拉取详情补全                 │
  │                                                      │
  ▼ 不存在                                               │
获取藏品详细数据                                          │
POST /h5/goods/archive {"archiveId":"54865"...}          │
  │                                                      │
  ▼                                                      │
写入 archives 表 + 提取 ipId                              │
  │                                                      │
  ▼                                                      │
获取IP信息                                               │
POST /h5/community/userHome {"uid":"30","fromType":"1"}  │
  │                                                      │
  ▼                                                      │
写入/更新 ips 表 (nickname, avatar, description, fans)    │
  │                                                      │
  └──────────────────────────────────────────────────────┘
```

### 1. 获取日历基础数据

Request URL: `POST https://api.x-metash.cn/h5/news/launchCalendar/list`

Payload:
```json
{"pageNum":1,"pageSize":50,"date":"2026-03-13","search":""}
```

Response:
```json
{
  "code" : 200,
  "msg" : "成功",
  "data" : [ {
    "id" : 4692,
    "archiveId" : null,
    "name" : "疏影恒春\u2022墨韵千载",
    "sellTime" : "2026-03-13 12:00:00",
    "amount" : 60.0,
    "count" : 12000,
    "priorityPurchaseNum" : 11400,
    "isPriorityPurchase" : true,
    "platformId" : 741,
    "platformName" : "鲸探",
    "platformImg" : "...",
    "ipName" : "故宫观唐",
    "ipAvatar" : "..."
  } ]
}
```

**采集字段**: id, name, sellTime, amount, count, platformId, platformName, platformImg, ipName, ipAvatar, priorityPurchaseNum, isPriorityPurchase, img

**处理逻辑**:
1. 按 source_id 查库，已存在则跳过（仅补全缺失的 platform/ip 关联）
2. 不存在则写入 `launch_calendar` 表，并触发详情获取

### 2. 获取日历详细数据

Request URL: `POST https://api.x-metash.cn/h5/news/launchCalendar/detailed`

Payload:
```json
{"id":4692}
```

Response 包含完整的 `contextCondition`（HTML购买阶段说明）、`containArchiveList`（包含藏品）、`associationArchiveList`（关联藏品），完整内容存入 `launch_detail.raw_json`。

**写入 `launch_detail` 表**: launch_id, priority_purchase_time, context_condition, status, raw_json

### 3. 关联藏品补齐

从 `raw_json` 中提取 `containArchiveList` 和 `associationArchiveList` 的 `associatedArchiveId`，去重后逐个检查 `archives` 表：

- **已存在且数据完整**: 直接跳过
- **已存在但缺失 IP信息/类型/数量**: 拉取详情补全
- **不存在**: 调用藏品详细数据接口创建记录

### 4. 获取藏品详细数据

Request URL: `POST https://api.x-metash.cn/h5/goods/archive`

Payload:
```json
{
  "archiveId": "54865",
  "platformId": "741",
  "active": "6",
  "page": 1,
  "pageSize": 20,
  "sellStatus": 1
}
```

**采集字段**: archiveId, archiveName, issueTime, archiveImage, totalGoodsCount, planeCodeJson[0].name (类型), isOpenAuction, isOpenWantBuy, ipId, ipName, ipAvatar, archiveDescription

### 5. 获取IP信息

Request URL: `POST https://api.x-metash.cn/h5/community/userHome`

Payload:
```json
{"uid":"30","fromType":"1"}
```

Response:
```json
{
  "code" : 200,
  "data" : {
    "uid" : 30,
    "nickname" : "故宫观唐",
    "avatar" : "...",
    "description" : "以故宫《石渠宝笈》著录历代书画为核心...",
    "userType" : 1
  }
}
```

**采集字段**: uid(source_uid), nickname(ip_name), avatar(ip_avatar), description, fans_count

**匹配逻辑**:
1. 先按 `source_uid` 查找
2. 再按 `ip_name + platform_id` 匹配
3. 都没有则创建新记录

### 日期遍历范围

- **全量爬取**: 从 today+7 开始往前遍历，连续 15 天无数据停止
- **定时任务**: 仅爬取今日和明日
- **近7天模式**: today-7 ~ today

## 第二阶段：藏品ID补齐（批量优化）

通过藏品详细数据接口补全藏品库中缺失的数据。

### 流程

```
获取数据库最大 numeric archive_id (max_id)
  │
  ▼
按批次处理 (每批 500 个ID)
  │
  ▼
批量查询数据库 ──► 得到本批已存在的 ID 集合
  │
  ▼
过滤出缺失的 ID 列表
  │
  ▼
分组并发拉取 (每组 5 个, 受信号量限制)
  │
  ▼
写入 archives 表 + 补全 IP 信息
  │
  ▼
每 20 条新增执行一次 commit
  │
  ▼
继续下一批 ... 直到 stop_id (15000)
```

### 优化点

| 优化 | 之前 | 之后 |
|------|------|------|
| 数据库查询 | 逐条 `db.get(Archive, id)` | 批量 `SELECT WHERE IN (500 ids)` |
| 网络请求 | 串行逐条请求 | 分组并发（5条/组，受信号量控制） |
| 提交策略 | 单条提交 | 批量提交（每 20 条新增） |

## 数据关系

```
Platform (平台)
  ├── IP (创作者)
  │     ├── LaunchCalendar (发行日历)
  │     │     └── LaunchDetail (发行详情, 含 raw_json)
  │     └── Archive (藏品)
  └── LaunchCalendar
  └── Archive
```

## 定时任务

| task_id | 名称 | 默认频率 | 功能 |
|---------|------|----------|------|
| `crawl_calendar` | 今日日历 | 每小时 | 爬取今日+明日日历 → 补全详情 → 补齐关联藏品 |
| `crawl_details` | 补全详情 | 每小时 | 查找缺少 launch_detail 的记录并获取 |
| `crawl_archives` | 藏品列表 | 每 6 小时 | 按分页更新藏品库数据 |
| `full_crawl` | 全量爬取 | 每天(禁用) | 从 today+7 往前爬至连续15天无数据 |
| `recent_7d_crawl` | 近7天 | 每天(禁用) | 重跑近7天日历+详情+关联藏品 |
| `archive_id_backfill` | 藏品ID补齐 | 每天(禁用) | 从 max_id 批量补齐到 15000 |

所有任务支持前端动态配置频率和开关。
