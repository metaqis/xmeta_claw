# 每日文章生成流程说明文档

## 一、整体架构

```
API 触发
  └─ service.generate_article("daily", target_date)
       ├─ [1] DailyReportSkill.get_data()       → analyzer.get_daily_data()
       ├─ [2] DailyReportSkill.generate_charts() → charts.generate_daily_charts()
       ├─ [3] llm.generate_article_content()
       │       ├─ 阶段1: _phase1_extract_facts()  → LLM 数据核实 (temperature=0.1)
       │       └─ 阶段2: skill.build_prompt()     → LLM 文章撰写 (temperature=0.3)
       ├─ [4] renderer.markdown_to_wechat_html()
       └─ [5] 存库 Article + ArticleImage
```

所有报告类型（日/周/月）共用同一个 `service.generate_article()` 入口，通过 `ReportSkill` 协议分发到对应子包；日报注册为 `"daily"` 类型，实现于 `reports/daily/__init__.py → DailyReportSkill`。

---

## 二、数据获取阶段（analyzer.py）

`get_daily_data(db, target_date)` 依次执行以下各阶段，最终返回一个大 dict 供图表和 Prompt 使用。

### 阶段1 — 发行基础数据

- **数据源**：`LaunchCalendar`（关联 `Platform`、`IP` 表）
- **查询函数**：`get_launch_rows()` + `summarize_launches()`
- **产出字段**：

| 字段 | 说明 |
|------|------|
| `launches` | 当日所有发行项列表，每项含 `launch_id / name / ip_name / price / count / value / platform_id / is_priority_purchase` 等 |
| `total_launches` | 今日发行项总数 |
| `total_supply` | 今日总发行份数 |
| `total_value` | 今日发行总价值（元） |
| `avg_price / max_price / min_price` | 发行价均值/最高/最低 |
| `ip_distribution` | IP 发行分布列表（按发行项数降序） |

### 阶捗2 — 发行数据增强

分6个子步骤，依次执行：

#### 3a. DB 含品增强

- **函数**：`enrich_daily_launches(db, launches)`
- **数据源**：
  - `LaunchDetail.raw_json` — 解析出 `containArchiveList`（含品列表）和 `associationArchiveList`（关联品列表）
  - `JingtanSkuHomepageDetail`（优先）/ `JingtanSkuWiki`（退化） — 补充含品元数据
- **每个含品补充的字段**：

| 字段 | 来源 | 说明 |
|------|------|------|
| `archive_id` | LaunchDetail | 含品 ID |
| `archive_name` | LaunchDetail | 含品名称 |
| `sales_num` | LaunchDetail | 发行量（该含品的总份数）|
| `percentage` | LaunchDetail | 配比%（中一份发行品可获该含品的比例）|
| `selling_count` | LaunchDetail | DB 快照：挂售数量 |
| `deal_count` | LaunchDetail | DB 快照：成交笔数 |
| `min_price` | LaunchDetail | DB 快照：最低挂单价 |
| `owner` | JingtanSkuHomepageDetail | 发行主体（机构名）|
| `author` | JingtanSkuHomepageDetail | 创作者/IP方 |
| `sku_desc` | JingtanSkuHomepageDetail | 藏品介绍文本（最长500字）|
| `owner_portfolio` | JingtanSkuHomepageDetail | 该发行主体近期其他藏品 |

#### 3b. 实时 API 市场数据

- **函数**：`_fetch_archives_live_market(archive_pairs)`
- **接口**：`POST /h5/goods/archiveGoods`（xmeta 平台），并发调用（`asyncio.gather`）
- **入参**：每个含品的 `(archive_id, platform_id)`，`sellStatus=2`（在售），`pageSize=1`
- **补充到含品的字段**：

| 字段 | 说明 |
|------|------|
| `live_total` | **实时**在售总挂单数（比 DB 快照的 `selling_count` 更新）|
| `live_min_price` | **实时**地板价（比 DB 快照的 `min_price` 更新）|

> 失败时静默跳过，不影响后续流程；Prompt 中优先使用这两个实时字段。

#### 3c. IP 深度画像

- **函数**：`get_ip_deep_analysis(db, ip_names, date_obj)`
- **数据源**：`LaunchCalendar`（统计发行次数）、`IP`（粉丝数、简介）
- **产出**（注入到 `ip_deep_analysis[ip_name]`）：

| 字段 | 说明 |
|------|------|
| `total_launches` | 历史总发行次数 |
| `recent_1y_launches` | 近一年发行次数（不含今日）|
| `fans_count` | IP 粉丝数（来自 `IP` 表）|
| `description` | IP 简介 |

#### 3d. 发行主体信息聚合

- 从 3a 的含品数据中收集所有 `owner`，批量查询：
  - `get_owner_sku_counts()` → 每个发行主体在鲸探上的历史总藏品数
  - `get_owner_portfolios()` → 每个发行主体近期4件代表作
  - `get_owner_other_ips()` → 每个发行主体合作过的所有 author（IP矩阵）
- 将上述信息作为 `owners` 数组注入 `ip_deep_analysis[ip_name]["owners"]`，每项含：
  - `name`：发行主体名
  - `total_sku_count`：历史发行总件数
  - `recent_works`：近期代表作名称列表
  - `other_ips`：旗下合作 IP 列表（发行商 IP 矩阵）

#### 3e. IP 上次发行记录

- **函数**：`_fetch_ip_last_launches(db, ip_names, before_date)`
- **数据源**：`LaunchCalendar` JOIN `IP`，取今日之前最近一次发行
- **注入**：`ip_deep_analysis[ip_name]["last_launch"]`，含：
  - `name`：作品名
  - `sell_time`：发行日期（YYYY-MM-DD）
  - `price`：发行价
  - `count`：发行量

#### 3f. IP 昨日市场快照

- **函数**：`_fetch_ip_market_snapshots(db, ip_names, yesterday, seven_ago)`
- **数据源**：`MarketIPSnapshot` 表（`stat_date` 在 [seven_ago, yesterday] 区间）
- **注入**：`ip_deep_analysis[ip_name]["market_snapshot"]`，结构：

```python
{
  "yesterday": {           # 昨日快照（文章分析用）
    "stat_date": "...",
    "deal_count": ...,         # 成交笔数
    "deal_count_rate": ...,    # 成交量日变化%
    "market_amount": ...,      # 总市值
    "market_amount_rate": ..., # 市值日变化%
    "avg_amount": ...,         # 均价
    "avg_amount_rate": ...,    # 均价日变化%
    "rank": ...,               # 排名
  },
  "trend_7d": [...]            # 近7天每日快照列表（可用于趋势分析）
}
```

### 阶段4 — 行情快照数据

- **函数**：`get_market_snapshot_data(db, target_date)`
- **数据源**：5 张市场快照表

| 查询 | 来源表 | 说明 |
|------|--------|------|
| `yesterday` / `day_before` | `MarketDailySummary` | 昨日/前日全市场汇总（成交量/成交额/总市值/Top板块/Top IP）|
| `summaries_7d` | `MarketDailySummary` | 近7天全市场汇总列表（用于折线图）|
| `top_planes` | `MarketPlaneSnapshot` | 昨日成交量 Top8 板块快照（含均价涨跌幅%、地板价）|
| `plane_census` | `MarketPlaneCensus` | 昨日 Top10 板块涨跌分布（上涨/下跌藏品数）|
| `top_census` | `MarketTopCensus` | 昨日行情分类成交统计（如鲸探50等）|
| `top_archives` | `MarketArchiveSnapshot` | 昨日各分类 Top5 藏品（按分类分组，用于图表）|
| `hot_archives_top10` | `MarketArchiveSnapshot` | 昨日全局成交量 Top10 藏品（不分类，用于文章分析）|

最终还预计算 `market_deal_change_pct`（市场成交量日环比%）注入返回 dict。

---

## 三、图表生成阶段（charts.py）

`generate_daily_charts(data, output_dir)` 按顺序生成以下图表，返回 `{chart_key: file_path}` 字典：

| chart_key | 图表类型 | 数据来源 | 说明 |
|-----------|----------|----------|------|
| `ip_distribution` | 横向条形图 | `data["ip_distribution"]` | 今日IP发行分布排行 |
| `launch_grid` | PIL 图片 | `enriched_launches` | 今日发行藏品封面卡片总览 |
| `cover` | PIL 图片 | 文字渲染 | 微信公众号封面图 |
| `market_trend_line` | 双轴折线图 | `market["summaries_7d"]` | 近7天市值（左轴）& 成交量（右轴）|
| `market_overview` | 柱状图 | `market["yesterday/day_before"]` | 昨日 vs 前日成交量对比 |
| `plane_deal_rank` | 横向条形图 | `market["top_planes"]` | Top8 板块成交量排行 |
| `plane_census` | 堆叠条形图 | `market["plane_census"]` | 板块藏品涨跌分布 |
| `top_archives` | 条形图 | `market["top_archives"]` | 各分类 Top5 藏品均价涨跌幅 |
| `hot_archives_top10` | 综合卡片图 | `market["hot_archives_top10"]` | 全局 Top10 热门藏品（成交量条形 × 均价涨跌染色 × 均价/地板价标签）|
| `ip_deal_rank` | 蝴蝶图（双向横向条形）| `ip_deep_analysis[*]["market_snapshot"]["yesterday"]` | 昨日热门 IP 成交 Top 5（左侧成交额¥、右侧成交笔数+环比） |

> `cover` 不计入 `available_charts`（封面不插入文章正文）。

---

## 四、LLM 生成阶段（llm.py）

日报采用**三次 LLM 调用**完成文章生成：

### 调用1 — 数据核实（阶段1）

```
model: qwen-plus
temperature: 0.1  ← 极低，确保严格忠于原始数据
max_tokens: 2000
system: ANALYSIS_SYSTEM_PROMPT（数据核实专员角色）
user:   build_analysis_prompt(data)
```

**目的**：防止 LLM 在阶段2写作时自行推算出错误数字（幻觉）。  
**输出**：结构化 JSON，包含：
- `launch_facts`：今日发行汇总数字
- `archive_premiums`：每件含品的溢价率（Python展开算式 → LLM 只需填结果）
- `ip_analysis`：每个 IP 的活跃度等级、上次发行、昨日市场数据

核实 JSON 以 `_verified_facts` 键注入到 `data` 副本，供阶段2 prompt 顶部引用。

### 调用2 — 文章撰写（阶段2）

```
model: qwen-plus
temperature: 0.3  ← 低温度，减少夸张表达
max_tokens: settings.LLM_MAX_TOKENS
system: SYSTEM_PROMPT（行业分析师角色 + 数据使用规则）
user:   build_daily_prompt(enriched_data, available_charts)
```

**Prompt 结构**（`build_daily_prompt`）：
1. 顶部嵌入阶段1核实 JSON（若存在）
2. 基础摘要（总发行数/总量/总价值）
3. 发行清单表格
4. 含品与市场数据（live_total / live_min_price / sku_desc）
5. IP 深度画像（活跃度 / 上次发行 / 昨日市场快照 / 发行商信息）
6. 二级市场行情（含板块/热门藏品 Top10）
7. 文章撰写四段结构要求（DAILY.md 规范）

**四段结构要求**（LLM 需按此撰写）：
- 段1 — 今日发售日历：含品的在售总量、地板价
- 段2 — 重点藏品解读：sku_desc + 发行量 + 溢价分析
- 段3 — IP与发行商分析：活跃度 + 上次发行 + 昨日市场 + 旗下IP矩阵
- 段4 — 昨日行情复盘：近7天市场趋势 + 板块 + 热门藏品 + IP排行

### 调用3 — 摘要生成

```
model: qwen-plus
temperature: 0.2
max_tokens: 200
system: "用一句话概括文章核心内容"
user:   文章前3000字
```

输出文章摘要，存入 `Article.summary`。

---

## 五、渲染与存储阶段（renderer.py / service.py）

### Markdown → 微信 HTML

`markdown_to_wechat_html(markdown, chart_urls)` 做两件事：

1. **图表替换**：将 `![标题](CHART:key)` 替换为对应的 `<img>` 标签
2. **样式注入**：将所有 HTML 标签替换为带内联样式的版本（微信不支持 CSS class）

风格：蓝白色调（主色 `#1677ff`），最大宽度 600px，适配手机阅读。

### 数据库存储

| 步骤 | 操作 |
|------|------|
| 文章记录 | 创建 `Article`（含 title / content_markdown / content_html / summary / cover_image_url）|
| 图表记录 | 每张图表创建一条 `ArticleImage`（含 image_type / file_path）|
| 状态流转 | `generating` → `draft`（成功）/ `failed`（异常）|
| 图表文件 | 存储于 `static/articles/{article_id}/` 下 |

> `Article.analysis_data` 保存原始 data dict 字符串，方便调试复现。

---

## 六、发布到微信流程（service.publish_article）

1. 遍历 `ArticleImage` 记录，将本地图片上传微信素材库（`wechat_client.upload_material()`）
2. 封面图上传后获取 `cover_media_id`
3. 其余图表上传获取 URL，重新替换 HTML 中的本地路径
4. 调用微信新增草稿接口，上传完整 HTML 草稿
5. 更新 Article 状态为 `published`

---

## 七、关键数据字段速查

### `enriched_launches[i]["contain_archives"][j]` 含品字段

| 字段 | 来源 | 含义 |
|------|------|------|
| `archive_id` | LaunchDetail | 含品 ID |
| `archive_name` | LaunchDetail | 含品名称 |
| `sales_num` | LaunchDetail | 发行总量 |
| `percentage` | LaunchDetail | 配比% |
| `selling_count` | LaunchDetail DB快照 | 挂售数（旧）|
| `min_price` | LaunchDetail DB快照 | 最低价（旧）|
| `live_total` | xmeta 实时API | 在售总量（最新）|
| `live_min_price` | xmeta 实时API | 地板价（最新）|
| `owner` | JingtanSkuHomepageDetail | 发行主体 |
| `author` | JingtanSkuHomepageDetail | 创作者/IP方 |
| `sku_desc` | JingtanSkuHomepageDetail | 藏品介绍 |

### `ip_deep_analysis[ip_name]` IP 画像字段

| 字段 | 来源 | 含义 |
|------|------|------|
| `total_launches` | LaunchCalendar | 历史总发行次数 |
| `recent_1y_launches` | LaunchCalendar | 近一年发行次数 |
| `fans_count` | IP 表 | 粉丝数 |
| `description` | IP 表 | IP简介 |
| `owners[].name` | 含品数据聚合 | 发行主体名 |
| `owners[].total_sku_count` | JingtanSkuHomepageDetail | 历史总藏品数 |
| `owners[].recent_works` | JingtanSkuHomepageDetail | 近期代表作 |
| `owners[].other_ips` | JingtanSkuHomepageDetail | 旗下合作IP列表 |
| `last_launch` | LaunchCalendar | 今日前最近发行记录 |
| `market_snapshot.yesterday` | MarketIPSnapshot | 昨日成交量/市值/均价 |
| `market_snapshot.trend_7d` | MarketIPSnapshot | 近7天日快照列表 |

---

## 八、常见问题

**Q: 含品的实时价格为何与 DB 中不同？**  
A: `live_total` / `live_min_price` 在每次生成时调用 xmeta 实时 API 获取，而 `selling_count` / `min_price` 是爬虫上次抓取时的快照。Prompt 中明确要求优先使用实时字段。

**Q: 为什么要两阶段 LLM 调用？**  
A: LLM 在直接撰写文章时容易自行推算溢价率、环比等数值并出错（幻觉）。阶段1用极低温度做「数据核实」，将关键数字固化为 JSON 事实，阶段2写作时强制引用，从根本上杜绝数值幻觉。

**Q: IP 上次发行/作品数据缺失怎么处理？**  
A: 当 `last_launch` 为 None（IP 仅在今日有发行记录）时，prompt 中不再注入"暂无记录"占位文本，writer 模板要求 LLM 直接跳过该行；若 `last_launch_time` 或 `last_launch_name` 任一为 null，整行省略。

**Q: `market_snapshot` 数据缺失时怎么处理？**  
A: `_fetch_ip_market_snapshots` 从 `MarketIPSnapshot` 查不到时返回空 dict，Prompt 中对应位置输出「暂无市场快照」，LLM 被明确要求不得编造。

**Q: 图表生成失败会影响文章生成吗？**  
A: 不会。`charts.py` 中每个图表函数失败返回空字符串，`generate_daily_charts` 只收集非空结果。`available_charts` 列表只包含成功生成的图表，LLM 被要求只插入列表中存在的图表标记。
