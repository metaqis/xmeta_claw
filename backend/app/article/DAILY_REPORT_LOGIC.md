# 数藏日报生成逻辑文档

> 文件路径：`backend/app/article/`  
> 生成入口：`POST /api/articles/generate` → `service.py::generate_article()`

---

## 一、整体流程

```
LaunchCalendar (DB)
        │
        ▼
  reports/daily/analyzer.py
  get_daily_data()
        │ ① 发行日历（LaunchCalendar + IP + Platform）
        │      └── queries/launch.py: get_launch_rows() + summarize_launches()
        │ ② 历史对比（昨日/上周同日发行数）
        │ ③ 近7天趋势（每日发行量/总价值）
        │      └── queries/trends.py: get_daily_trend()
        │ ④ queries/enrichment.py: enrich_daily_launches()
        │      ├── get_launch_details() → LaunchDetail.raw_json → containArchiveList
        │      │     └── 含品：配比% / 发行量 / 市场最低价 / 成交数
        │      └── match_jingtan_archives()
        │            └── JingtanSkuHomepageDetail / JingtanSkuWiki
        │                  → author / owner / sku_desc / 图片
        │ ⑤ queries/enrichment.py: get_ip_deep_analysis()
        │      ├── IP历史总发行次数（全量）
        │      ├── IP近30天发行次数
        │      ├── IP粉丝数 / IP简介
        │      └── 发行主体（owner）：get_owner_sku_counts() + get_owner_portfolios()
        │
        ▼
  reports/daily/charts.py
  generate_daily_charts()
        │ • charts/cards.py:  launch_grid.png  — 当日发行总览卡片图
        │ • charts/trend.py:  daily_trend.png  — 近7天发行趋势柱状图
        │ • charts/trend.py:  value_trend.png  — 近7天价值趋势折线图
        │ • charts/cover.py:  cover.png        — 微信封面图
        │
        ▼
  llm.py
  generate_article_content()
        │ • get_skill("daily").build_prompt() → reports/daily/prompt.py
        │ • 调用 qwen-plus（DashScope OpenAI 兼容接口）
        │ • 生成摘要（二次 LLM 调用，≤100字）
        │
        ▼
  service.py
        │ • 将图表上传微信素材库（wechat_client）
        │ • renderer.py: markdown_to_wechat_html() → 内联样式 HTML
        │ • wechat_client.create_draft()
        │ • 写入 articles + article_images 表
        ▼
      Article(DB)  status=draft
```

---

## 二、数据层详解

### 2.1 `get_daily_data(db, target_date)` 返回字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | str | 目标日期 YYYY-MM-DD |
| `total_launches` | int | 当日发行总项数 |
| `total_supply` | int | 当日总发行量（份） |
| `total_value` | float | 总发行价值（¥） |
| `avg_price` | float | 均价 |
| `max_price` / `min_price` | float | 最高/最低价 |
| `launches` | list[dict] | 发行项列表（含 launch_id, name, ip_name, price, count, img 等） |
| `enriched_launches` | list[dict] | 增强发行项（含 contain_archives + association_archives） |
| `ip_distribution` | list[dict] | IP发行分布（按发行次数降序） |
| `daily_trend` | list[dict] | 近7天每日发行量/总价值 |
| `yesterday_launches` | int | 昨日发行项数 |
| `last_week_same_day_launches` | int | 上周同日发行项数 |
| `ip_recent_30d_history` | dict | IP → 近30天发行次数 |
| `ip_deep_analysis` | dict | IP → 深度画像（见下） |

### 2.2 `enriched_launches[i]` 中每条 `contain_archives` 字段

| 字段 | 来源 | 说明 |
|------|------|------|
| `archive_name` | LaunchDetail.raw_json | 含品藏品名 |
| `percentage` | LaunchDetail.raw_json | 中签配比（%） |
| `sales_num` | LaunchDetail.raw_json | 该含品发行量 |
| `min_price` | LaunchDetail.raw_json | 鲸探当前最低在售价 |
| `deal_count` | LaunchDetail.raw_json | 成交笔数 |
| `selling_count` | LaunchDetail.raw_json | 当前在售数量 |
| `owner` | JingtanSkuHomepageDetail | 发行主体（机构名） |
| `author` | JingtanSkuHomepageDetail | 艺术家/创作者 |
| `sku_desc` | JingtanSkuHomepageDetail | 藏品介绍（≤500字) |
| `owner_portfolio` | JingtanSkuHomepageDetail | 该主体近5件藏品 |
| `author_portfolio` | JingtanSkuHomepageDetail | 该创作者近5件藏品 |

### 2.3 `ip_deep_analysis[ip_name]` 字段

| 字段 | 说明 |
|------|------|
| `total_launches` | 该IP在 launch_calendar 中的历史总发行次数 |
| `recent_30d_launches` | 近30天发行次数（不含当日） |
| `fans_count` | IP粉丝数（来自 ips 表） |
| `description` | IP简介（来自 ips 表） |
| `owners` | list of `{name, total_sku_count, recent_works}` |
| `owners[].name` | 发行主体名称 |
| `owners[].total_sku_count` | 该主体在鲸探上的历史藏品总数 |
| `owners[].recent_works` | 该主体近期代表作（≤4件，名称列表） |

---

## 三、图表层详解（`charts/`）

### 3.1 `charts/cards.py: generate_launch_grid(launches, output_dir)` — 当日发行总览

**输入：** `enriched_launches` 列表（最多10项）

**输出：** PNG 图片，900px 宽，卡片式布局

**卡片结构（每张）：**
```
┌──────────────────────────────────────────────────────────┐
│ [蓝色顶条] IP名称                    优先购N份 | 发售HH:MM │
├──────────┬───────────────────────────────────────────────┤
│          │ 发行名称（最多2行）                             │
│  日历    │ [¥价格 徽章] [N份 徽章] [总值¥X 徽章]          │
│  封面    │ [★ 优先购N份(X%) 徽章]（若有）                 │
│ 180×180  │ 发行方：XXX机构                                │
│          │ 包含 N 件藏品                                  │
│ 10,000份 │ ┌────┬────┬────┬────┐                        │
│  (药丸)  │ │含品│含品│含品│含品│  ← 圆角缩略图100×100    │
│          │ │80% │20% │    │    │  ← 配比角标             │
│          │ │名称│名称│    │    │  ← 居中文字             │
│          │ │¥X  │¥Y  │    │    │  ← 绿色市场价+成交数   │
│          │ └────┴────┴────┴────┘                        │
└──────────┴───────────────────────────────────────────────┘
```

**颜色规范：**
- 背景：`#EBF0FA`（淡蓝灰）
- 卡片：白色 + 双层软阴影 + `radius=10` 圆角
- 顶条：`#1677FF`（主蓝）
- 全局 Header：`#0A1437`（深海蓝）
- 发行价徽章：蓝底；份数徽章：灰底；总值徽章：绿底；优先购徽章：金底
- 市场价：绿色；成交数：灰色

---

## 四、Prompt 层详解（`reports/daily/prompt.py`）

### 4.1 日报 Prompt 结构

```
系统角色 (SYSTEM_PROMPT)                  ← reports/daily/prompt.py
  - 专业数藏分析师+自媒体作者人设
  - 微信公众号格式规范（标题、加粗、图表标记）
  - 严禁编造数字

用户 Prompt (build_daily_prompt)          ← reports/daily/prompt.py
  ├── 基础数据块（日期/总量/均价/对比）
  ├── 发行清单表格（各项名称/IP/价格/数量/总值/优先购）
  ├── 含品与市场数据（每发行项的含品名/配比/市场价/溢价估算/藏品介绍）
  ├── IP深度画像（历史发行次数/活跃度/发行主体背景/近期代表作）
  ├── 近7天趋势数据
  └── 文章结构指令（强制章节+字数要求）
```

### 4.2 文章要求的章节结构

1. **标题**：含日期 + 核心亮点关键词
2. **开篇导语**：2-3句话钩子
3. **`![发行藏品总览](CHART:launch_grid)`**（若可用）
4. **今日速览**：核心数字 + 与昨日/上周对比
5. **IP 格局解析**：每个IP子节（活跃度 + 发行主体背景 + 历史市场表现）
6. **重点藏品解读**：2-3件含品（题材 + 稀缺性 + 市场价 + 参考建议）
7. **二级市场表现**：溢价最高 vs 最低藏品
8. **总结与明日展望**
9. **免责声明**（引用块格式）

---

## 五、模块结构

```
app/article/
├── service.py              — 公共 API 入口（generate_article / publish_article 等）
├── wechat_client.py        — 微信公众号 API 封装
├── renderer.py             — Markdown → 微信内联样式 HTML
├── llm.py                  — LLM 调用中枢（通过 get_skill 注册表分发）
├── queries/                — 原子 DB 查询层
│   ├── launch.py           — get_launch_rows, summarize_launches
│   ├── trends.py           — get_daily_trend
│   └── enrichment.py       — get_launch_details, match_jingtan_archives,
│                             get_owner_portfolios, get_author_portfolios,
│                             enrich_daily_launches, get_ip_deep_analysis,
│                             get_owner_sku_counts
├── charts/                 — 图表生成层
│   ├── base.py             — matplotlib 配置 + setup_ax / save_fig / ensure_dir
│   ├── trend.py            — chart_daily_trend, chart_value_trend, chart_weekly_breakdown
│   ├── ranking.py          — chart_ip_ranking
│   ├── cover.py            — generate_cover（微信封面图）
│   └── cards.py            — generate_launch_grid（PIL 卡片拼图）
└── reports/                — Skill 化报告单元（扩展新报告类型只需在此添加子包）
    ├── __init__.py         — ReportSkill 协议 + @register 装饰器 + get_skill()
    ├── daily/              — 日报（@register("daily")）
    │   ├── analyzer.py     — get_daily_data()
    │   ├── charts.py       — generate_daily_charts()
    │   └── prompt.py       — SYSTEM_PROMPT + build_daily_prompt()
    ├── weekly/             — 周报（@register("weekly")）
    │   ├── analyzer.py     — get_weekly_data()
    │   ├── charts.py       — generate_weekly_charts()
    │   └── prompt.py       — build_weekly_prompt()
    └── monthly/            — 月报（@register("monthly")）
        ├── analyzer.py     — get_monthly_data()
        ├── charts.py       — generate_monthly_charts()
        └── prompt.py       — build_monthly_prompt()
```

### Skill 扩展方式

添加新报告类型（如 yearly）只需三步，**无需修改 service.py**：
1. 新建 `reports/yearly/` 子包，实现 `get_data / generate_charts / build_prompt`
2. 用 `@register("yearly")` 装饰实现类
3. 在 `llm.py` 中 `import app.article.reports.yearly`（触发注册）

---

## 六、存储层（service.py）

```python
Article {
  article_type = "daily"
  data_date    = "YYYY-MM-DD"
  status       = "draft"          # 生成后
  content_html = <wechat html>    # 微信内联样式HTML
  content_markdown = <原始MD>
  wechat_media_id  = <草稿media_id>  # 创建草稿后
}

ArticleImage {
  image_type = "launch_grid" | "daily_trend"
  file_path  = "static/articles/{date}/launch_grid.png"
  wechat_media_url = <上传微信后的URL>
}
```

---

## 七、触发方式

### 手动触发（API）
```
POST /api/articles/generate
Body: {"article_type": "daily", "target_date": "2026-04-09"}
```

### 定时触发（scheduler）
- 每日 `10:00` 自动执行当日日报生成
- 配置在 `scheduler/tasks.py`

### 微信发布
- 生成后状态为 `draft`，需在微信公众号后台手动审核发布
- `freepublish/submit` API 需要认证服务号权限，当前账号不支持自动发布

---

## 八、依赖服务

| 服务 | 配置项 | 用途 |
|------|--------|------|
| PostgreSQL | `DATABASE_URL` | 所有数据来源 |
| DashScope (qwen-plus) | `LLM_API_KEY` / `LLM_BASE_URL` | 文章生成 |
| 微信公众号 | `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 上传图片/创建草稿 |

---

## 九、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 含品数据为空 | LaunchDetail 未抓取 | 先运行发行详情爬虫 |
| owner/author 为空 | JingtanSkuHomepageDetail 未匹配 | 运行鲸探SKU抓取任务 |
| 图片生成失败 | 封面URL超时或404 | 检查网络/URL有效性 |
| 微信上传失败 | access_token 过期 | 重启自动刷新；检查AppID/Secret |
| LLM 输出超短 | max_tokens 设置过低 | 调整 `config.LLM_MAX_TOKENS` |
