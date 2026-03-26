# 爬虫流程

## 总体架构

> 接口样本已按单接口拆分至 [api_example/README.md](api_example/README.md)，后续新增接口时请同步维护该目录。

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

## 系统分层架构

整个系统可以分成 6 层：前端展示层、API 接入层、业务编排层、Agent 层、数据存储层、外部数据源层。

```
┌──────────────────────────────────────────────────────────────┐
│                       Frontend / React                        │
│ Dashboard · Calendar · Archives · IPs · Tasks · Agent        │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP / SSE / JWT
┌──────────────────────────────▼───────────────────────────────┐
│                      FastAPI API 接入层                       │
│ auth / calendar / archives / ips / stats / crawler / tasks / agent │
└───────────────┬──────────────────────┬───────────────────────┘
                │                      │
                │                      │
┌───────────────▼──────────────┐  ┌────▼──────────────────────┐
│      爬虫/任务业务编排层       │  │       Agent 编排层          │
│ scheduler.tasks              │  │ agent.service              │
│ crawler.*                    │  │ agent.executor / tools     │
│ 负责数据拉取、补齐、调度        │  │ 负责意图识别、工具路由、流式回答 │
└───────────────┬──────────────┘  └────┬──────────────────────┘
                │                        │
                ├──────────────┬─────────┤
                │              │         │
┌───────────────▼───────┐ ┌────▼───────┐ ┌────────────────────▼───┐
│ PostgreSQL / ORM 模型  │ │ Redis缓存  │ │ 外部鲸探/X-Meta 实时接口 │
│ 平台/IP/日历/详情/藏品   │ │ 热点缓存    │ │ 日历/详情/行情/板块/IP等 │
│ 任务配置/运行记录/聊天   │ │            │ │                        │
└───────────────────────┘ └────────────┘ └────────────────────────┘
```

### 各层职责

- 前端层：负责登录鉴权、数据看板、任务管理、Agent 对话展示与 SSE 流式接收。
- API 层：对外暴露 REST / SSE 接口，做鉴权、参数校验、分页与响应整形。
- 爬虫业务层：封装外部接口访问、数据清洗、关联补齐、定时调度和手动触发。
- Agent 层：根据用户意图在数据库工具与实时接口工具之间做编排，输出自然语言答案。
- 数据层：保存平台、IP、发行日历、发行详情、藏品、任务运行记录、聊天会话与消息。
- 外部数据源层：提供日历、藏品详情、IP 信息、实时行情、板块与排行等原始数据。

## 核心模块职责

### 后端模块

| 模块 | 作用 |
|------|------|
| `app/main.py` | FastAPI 生命周期入口：初始化数据库、创建管理员、启动调度器、关闭爬虫连接池与缓存 |
| `app/api/*` | 面向前端的业务接口，按认证、日历、藏品、IP、统计、任务、爬虫、Agent 分组 |
| `app/crawler/*` | 爬虫实现与数据补齐逻辑，包括日历、详情、藏品、IP、回填任务 |
| `app/scheduler/tasks.py` | APScheduler 任务注册、任务运行记录、日志落库、取消执行 |
| `app/agent/*` | LLM 客户端、系统提示词、工具定义、工具执行器、SSE 流式编排 |
| `app/database/*` | 异步数据库连接与 ORM 模型 |
| `app/core/*` | 配置、鉴权、缓存等基础设施能力 |

### 数据模型主干

| 模型 | 说明 |
|------|------|
| `Platform` | 平台主表 |
| `IP` | IP / 发行方 / 创作者信息，保存 `source_uid`、头像、描述、粉丝数 |
| `LaunchCalendar` | 发行日历主表 |
| `LaunchDetail` | 发行详情表，保存完整原始响应 `raw_json` |
| `Archive` | 藏品主表，关联平台与 IP |
| `TaskConfig` | 定时任务配置 |
| `TaskRun` / `TaskRunLog` | 任务运行记录与日志 |
| `ChatSession` / `ChatMessage` | Agent 会话和消息流水 |

## 系统主链路

### 1. 数据采集链路

```
Scheduler / 管理员手动触发
  │
  ▼
任务编排（tasks.py / crawler.py）
  │
  ▼
CrawlerClient 发起外部请求
  │
  ▼
清洗、去重、关联平台/IP/藏品
  │
  ▼
写入 PostgreSQL
  │
  ▼
前端页面 / Agent 工具读取数据库与实时接口
```

### 2. 用户查询链路

```
前端页面 / Agent 输入问题
  │
  ▼
FastAPI 鉴权 + 路由分发
  │
  ├─ 普通业务查询：直接查数据库 / 聚合统计
  │
  └─ Agent 查询：进入 stream_chat → LLM → Tool → SSE 回流前端
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

## 爬虫业务链路

### 任务触发来源

系统中的爬虫任务有两种触发方式：

1. **定时触发**：`app/scheduler/tasks.py` 在系统启动时加载 `TaskConfig`，注册到 APScheduler。
2. **手动触发**：管理员通过 `/tasks/{task_id}/run` 或 `/crawler/*` 接口启动后台任务。

### 任务运行生命周期

```
创建 TaskRun(queued)
  │
  ▼
切换为 running
  │
  ├─ 按步骤写入 TaskRunLog
  │
  ├─ 成功 -> success
  │
  ├─ 失败 -> failed
  │
  └─ 人工停止 -> cancelling / cancelled
```

### 爬虫任务编排关系

| task_id | 核心动作 |
|---------|----------|
| `crawl_calendar` | 拉取今日/明日日历 → 补发行详情 → 回填关联藏品 |
| `crawl_details` | 仅补齐缺失的发行详情 |
| `crawl_archives` | 更新藏品库 |
| `full_crawl` | 从未来 7 天起向前回扫，直到连续 15 天无数据，再统一补详情、补关联、刷新藏品库 |
| `recent_7d_crawl` | 重跑近 7 天日历与关联数据 |
| `archive_id_backfill` | 从数据库最大数值型 `archive_id` 向下批量扫描补齐 |
| `ip_uid_backfill` | 通过现有藏品/IP 关系回填 `source_uid` |

### 爬虫链路中的“业务闭环”

爬虫并不是简单抓取单接口，而是围绕“**日历 → 详情 → 关联藏品 → IP → 藏品库 → 后续查询**”形成闭环：

1. 日历负责发现增量发行事件。
2. 详情负责补足购买说明、状态、关联藏品集合。
3. 关联藏品补齐把日历事件转换成可查询的 `Archive` 主数据。
4. IP 信息补齐把藏品和发行方连接起来。
5. 藏品库补齐与 `archive_id` 回填负责补全历史存量。
6. 最终这些数据为 Dashboard、列表页、Agent 问答提供稳定底座。

## Agent 相关流程

### Agent 在系统中的位置

Agent 不是单独的爬虫，而是一个“**自然语言入口 + 工具编排层**”。

- 前端页面：`frontend/src/pages/agent/index.tsx`
- API 入口：`/agent/sessions`、`/agent/chat`
- 编排核心：`app/agent/service.py`
- 工具执行：`app/agent/executor.py`
- 工具定义：`app/agent/tools.py`
- 模型接入：`app/agent/llm.py`

### Agent 会话链路

```
用户输入问题
  │
  ▼
前端调用 /agent/chat（SSE）
  │
  ▼
stream_chat 校验会话 / 保存用户消息
  │
  ▼
加载最近历史消息 + 最近实体上下文 + 候选项
  │
  ▼
意图识别（发行日历 / 行情 / 走势 / 热榜 / IP / 板块 / 统计 / 详情）
  │
  ▼
按意图筛选可用工具
  │
  ▼
调用 LLM
  │
  ├─ 无工具调用：直接流式输出答案
  │
  └─ 有工具调用：执行工具 → 写入 tool 消息 → 再次调用 LLM 生成最终答案
  │
  ▼
SSE 持续回传 tool_call / content / done
  │
  ▼
前端边接收边渲染，并附带后续建议问题
```

### Agent 的核心决策逻辑

#### 1. 先识别意图，再限制工具范围

`service.py` 会根据关键词识别：

- 发行日历
- 行情查询
- 价格走势
- 热榜 / 排行
- IP 查询 / IP 排行
- 板块查询
- 统计概览
- 详情查询

识别结果会决定本轮只暴露哪些工具给 LLM，避免模型无关扩展。

#### 2. 先做实体确认，再查详情 / 行情

当用户只给名称、不提供唯一 ID 时，Agent 会优先走实体解析：

1. `resolve_entities`
2. 数据库搜索 `search_archives` / `search_ips`
3. 在线搜索 `online_search_archives` / `online_search_ips`

如果候选不唯一，则先要求用户选“第 1 个 / 第 2 个”，避免误查。

#### 3. 数据来源分层

Agent 工具分成两类：

- **数据库静态工具**：查历史沉淀数据，如藏品详情、IP 详情、日历、数据库统计。
- **实时接口工具**：查今日热榜、价格走势、板块统计、IP 排名、分类排行等动态数据。

因此 Agent 回答本质上是“**数据库基底 + 实时接口增强**”。

### Agent 工具分组

| 分组 | 典型工具 | 作用 |
|------|----------|------|
| 实体解析 | `resolve_entities` | 从自然语言里识别藏品/IP |
| 数据库检索 | `search_archives`、`get_archive_detail`、`search_ips`、`get_ip_detail` | 查本地沉淀数据 |
| 在线补充 | `online_search_archives`、`online_search_ips` | 当数据库结果不足时补候选 |
| 日历工具 | `get_upcoming_launches` | 查近期发行 |
| 统计工具 | `get_db_stats` | 查库内总体规模 |
| 实时行情工具 | `get_archive_market`、`get_archive_price_trend` | 查单个藏品实时行情与走势 |
| 排行/板块工具 | `get_hot_archives`、`get_market_categories`、`get_category_archives`、`get_ip_ranking`、`get_sector_stats` | 查榜单、分类、板块、IP 热度 |

### Agent 消息持久化策略

每轮对话都会写入 `ChatMessage`：

- `user`：用户原始问题
- `assistant`：模型回答，或工具调用描述（`tool_calls`）
- `tool`：每个工具的原始结果

这样做的目的：

1. 让后续追问可以复用最近上下文。
2. 支持“选第 2 个”“看这个”“它最近怎么样”这类省略式追问。
3. 在长会话中可截断过长的历史工具结果，控制 token 成本。

### 前端 Agent 渲染流程

前端通过 SSE 接收 4 类事件：

- `tool_call`：显示“正在查询日历/热榜/详情”等步骤标签
- `content`：逐段拼接回答正文
- `done`：结束本轮，并携带建议追问
- `error`：显示异常

因此用户看到的是一个“边查边回、可连续追问”的聊天式数据助手，而不是一次性阻塞式接口。

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

- 接口：`POST /h5/news/launchCalendar/list`
- 采集字段：`id`, `name`, `sellTime`, `amount`, `count`, `platformId`, `platformName`, `platformImg`, `ipName`, `ipAvatar`, `priorityPurchaseNum`, `isPriorityPurchase`, `img`
- 处理逻辑：
  1. 按 `source_id` 查库，已存在则跳过，仅补全缺失的平台 / IP 关联
  2. 不存在则写入 `launch_calendar` 表，并触发详情获取

### 2. 获取日历详细数据

- 接口：`POST /h5/news/launchCalendar/detailed`
- 关键内容：`contextCondition`、`containArchiveList`、`associationArchiveList`
- 存储方式：完整响应写入 `launch_detail.raw_json`
- 主要字段：`launch_id`, `priority_purchase_time`, `context_condition`, `status`, `raw_json`

### 3. 关联藏品补齐

从 `raw_json` 中提取 `containArchiveList` 和 `associationArchiveList` 的 `associatedArchiveId`，去重后逐个检查 `archives` 表：

- 已存在且数据完整：直接跳过
- 已存在但缺失 IP 信息 / 类型 / 数量：拉取详情补全
- 不存在：调用藏品详细数据接口创建记录

### 4. 获取藏品详细数据

- 接口：`POST /h5/goods/archive`
- 采集字段：`archiveId`, `archiveName`, `issueTime`, `archiveImage`, `totalGoodsCount`, `planeCodeJson[0].name`, `isOpenAuction`, `isOpenWantBuy`, `ipId`, `ipName`, `ipAvatar`, `archiveDescription`

### 5. 获取IP信息

- 接口：`POST /h5/community/userHome`
- 采集字段：`uid(source_uid)`, `nickname(ip_name)`, `avatar(ip_avatar)`, `description`, `fans_count`
- 匹配逻辑：
  1. 先按 `source_uid` 查找
  2. 再按 `ip_name + platform_id` 匹配
  3. 都没有则创建新记录

### 日期遍历范围

- 全量爬取：从 today+7 开始往前遍历，连续 15 天无数据停止
- 定时任务：仅爬取今日和明日
- 近7天模式：today-7 ~ today

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
继续下一批 ... 直到 stop_id (10000)
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

## 任务清单与触发入口

### 统一调度入口

所有可调度任务都在 `app/scheduler/tasks.py` 的 `TASK_DEFINITIONS` 中注册，并由 `TaskConfig` 控制开关与频率。系统启动时会自动补齐缺失配置，并将启用项注册到 APScheduler。

### 任务总表

| task_id | 当前名称 | 默认频率 | 主要模块 | 简要说明 |
|---------|----------|----------|----------|----------|
| `crawl_calendar` | 今明日日历链路 | 每小时 | `scheduler/tasks.py` + `calendar_crawler.py` + `launch_detail_crawler.py` + `calendar_archive_backfill.py` | 抓取今日与明日日历，随后补齐发行详情，并基于详情里的关联藏品列表补齐 `Archive` |
| `crawl_details` | 发行详情补齐 | 每小时 | `scheduler/tasks.py` + `launch_detail_crawler.py` | 扫描缺少 `LaunchDetail` 的发行记录并逐条补齐详情 |
| `crawl_archives` | 藏品库同步 | 每 6 小时 | `scheduler/tasks.py` + `archive_crawler.py` | 分页同步鲸探藏品列表，并按需补齐类型、数量和 IP 资料 |
| `full_crawl` | 全量回扫链路 | 每天（默认禁用） | `scheduler/tasks.py` + `calendar_crawler.py` + `launch_detail_crawler.py` + `calendar_archive_backfill.py` + `archive_crawler.py` | 从 `today+7` 开始向前回扫日历，直到连续 15 天无数据，再统一补详情、关联藏品与藏品库 |
| `recent_7d_crawl` | 近7天重跑链路 | 每天（默认禁用） | `scheduler/tasks.py` + `calendar_crawler.py` + `launch_detail_crawler.py` + `calendar_archive_backfill.py` + `archive_crawler.py` | 重跑近 7 天日历链路，适合补偿近期接口抖动或脏数据 |
| `archive_id_backfill` | 藏品ID倒序补齐 | 每天（默认禁用） | `scheduler/tasks.py` + `archive_id_backfill.py` | 从 `archive_id=15000` 向下扫描到 `10000`，跳过已存在记录与 miss 记录 |
| `archive_id_refresh_near_max` | 最大ID邻域刷新 | 每 6 小时（默认禁用） | `scheduler/tasks.py` + `archive_id_backfill.py` | 围绕当前最大 `archive_id` 前后各 100 强制刷新，用于修复新近藏品的字段不完整问题 |
| `ip_uid_backfill` | IP source_uid补齐 | 每天（默认禁用） | `scheduler/tasks.py` + `ip_uid_backfill.py` | 从已关联藏品详情中提取 `ipId`，回填 `IP.source_uid` 并顺带补资料 |
| `import_planes_weekly` | 板块周导入 | 每周一 03:00 | `scheduler/tasks.py` + `services/plane_importer.py` | 导入板块数据，属于数据同步任务，不属于爬虫主链路 |
| `crawl_jingtan_sku_wiki` | 鲸探 SKU Wiki 同步 | 每天（默认禁用） | `scheduler/tasks.py` + `jingtan_sku_wiki_crawler.py` | 按一级分类分页抓取 AntFans SKU Wiki 列表，更新本地 `JingtanSkuWiki` |
| `crawl_jingtan_sku_details` | 鲸探 SKU 详情同步 | 每天（默认禁用） | `scheduler/tasks.py` + `jingtan_sku_homepage_detail_crawler.py` | 遍历 Wiki 中已有 `sku_id`，只补齐 `JingtanSkuHomepageDetail` 中缺失的详情记录；详情优先入库，Wiki 表尽力同步 |
| `crawl_jingtan_sku_details_backfill` | 鲸探 SKU 倒序回填 | 每天（默认禁用） | `scheduler/tasks.py` + `jingtan_sku_homepage_detail_crawler.py` | 以最大 `sku_id` 为起点向下扫描，只补齐 `JingtanSkuHomepageDetail` 中缺失的鲸探详情数据；回填结束后输出 `skipped_sku_ids` 与 `failed_sku_ids` |

### 手动触发入口

| 入口 | 用途 | 说明 |
|------|------|------|
| `/tasks/{task_id}/run` | 通用任务入口 | 会创建 `TaskRun` / `TaskRunLog`，适合运维侧统一观测、取消和追踪 |
| `/crawler/full` | 手动触发全量回扫链路 | 现已转入统一任务体系，内部触发 `full_crawl`，会返回 `run_id` 以便追踪 |
| `/crawler/calendar/{date}` | 单日日历抓取 | 仍是参数化特例入口，执行指定日期的日历抓取与关联藏品补齐，暂未纳入统一任务体系 |
| `/crawler/jingtan/sku-wiki` | 手动触发 SKU Wiki | 现已转入统一任务体系，内部触发 `crawl_jingtan_sku_wiki`，会返回 `run_id` |

### Crawler 模块职责对照

| 模块 | 核心职责 | 备注 |
|------|----------|------|
| `platform_ip_service.py` | 提供平台与 IP 的创建、补全、查找共享能力 | 被日历抓取、藏品详情入库、藏品库同步共同复用 |
| `launch_detail_service.py` | 提供发行详情拉取与落库共享能力 | 被日历抓取和缺失详情补齐共同复用 |
| `calendar_crawler.py` | 抓发行日历列表、补平台/IP 关系，并复用共享能力补发行详情 | 负责日历发现与首轮详情落库 |
| `launch_detail_crawler.py` | 扫描缺失详情的发行记录并补齐 `LaunchDetail` | 现在与日历抓取共用同一套详情保存逻辑 |
| `archive_detail_service.py` | 提供藏品详情拉取、补齐判定与详情入库共享能力 | 被藏品库同步、日历关联回填、ID 倒序补齐、IP UID 补齐复用 |
| `calendar_archive_backfill.py` | 从 `LaunchDetail.raw_json` 中提取关联藏品并补齐 `Archive` / `IP` | 实际更像“发行详情关联藏品回填器” |
| `archive_crawler.py` | 分页同步藏品库列表，并按需拉详情补类型、数量和 IP | 是“藏品库同步”，不只是简单列表抓取 |
| `archive_id_backfill.py` | 通过 `archive_id` 倒序补历史藏品，并支持最大 ID 邻域刷新 | 现在直接复用共享的藏品详情能力 |
| `ip_uid_backfill.py` | 用藏品详情反向补齐 `IP.source_uid`，并拉取 IP 主页资料 | 解决历史数据中 IP 唯一标识缺失问题 |
| `jingtan_sku_wiki_crawler.py` | 抓 AntFans SKU Wiki 列表 | 主要承担 SKU 发现与分类归档 |
| `jingtan_sku_homepage_detail_crawler.py` | 抓 AntFans SKU 详情，并同步明细表与 Wiki 表 | 同时承担分类猜测与回填逻辑 |

### 命名与职责优化结论

1. 保留 `task_id` 与数据库结构不变，只调整人类可读名称、描述和内部函数命名，避免影响前端、调度配置和历史运行记录。
2. 将 `crawl_calendar` 明确表达为“今明日日历链路”，因为它实际不止抓日历，还会补详情和关联藏品。
3. 将 `crawl_archives` 明确表达为“藏品库同步”，因为它不仅拉列表，还会在必要时拉详情修正 `archive_type`、`total_goods_count` 和 `IP` 关系。
4. 将 `crawl_jingtan_sku_details_backfill` 对应的内部命名统一为“descending backfill”，避免 `desc` 被误解为 description。
5. 将可无参手动入口尽量收敛到统一任务体系，当前 `/crawler/full` 与 `/crawler/jingtan/sku-wiki` 已能复用 `TaskRun / TaskRunLog` 链路。
6. 将最大 ID 邻域刷新恢复为“围绕当前最大 `archive_id`”执行，避免函数名与实际行为不一致。
7. 已抽离 `launch_detail_service.py`、`archive_detail_service.py`、`platform_ip_service.py` 三个共享模块，当前主要重复逻辑已进一步收敛，后续可以继续按“列表抓取 / 详情补齐 / 回填编排”三层再细化边界。

所有任务仍支持前端动态配置频率和开关。

## 接口样本维护

`spider_process.md` 仅保留爬取流程、数据关系与调度说明。

所有外部接口的请求样本与完整原始响应已迁移到 [api_example/README.md](api_example/README.md)，后续请仅维护该目录。

当前已拆分的接口包括：

- 日历基础数据 / 日历详情
- 藏品详情 / IP 信息
- 价格查询 / 销售折线图 / 版块统计
- 市场热榜 / 行情分类 / 分类热门成交 / IP 热榜 / 板块成交 / 板块列表
- 在线藏品 / IP 搜索
