# 每日微信公众号文章生成 — 业务流程文档

> 本文档描述数藏日报从数据采集到微信发布的完整流程、各模块职责、数据流转以及质量保障机制。

---

## 一、系统架构总览

```
API 请求 (POST /articles/generate {type: "daily"})
   │
   ├─ [1] 数据采集与分析 ── analyzer.py
   │       ├─ 阶段1: 发行基础数据（LaunchCalendar）
   │       ├─ 阶段3a: DB含品增强（LaunchDetail + JingtanSkuHomepageDetail）
   │       ├─ 阶段3b: 实时API — 含品在售量/地板价（h5/goods/archiveGoods）
   │       ├─ 阶段3c: IP深度画像（历史发行/粉丝/活跃度）
   │       ├─ 阶段3d: IP上次发行记录
   │       ├─ 阶段3e: IP昨日市场快照（MarketIPSnapshot）
   │       ├─ 阶段3f: 发行主体旗下IP/作品
   │       └─ 阶段4: 行情快照（近7天市场汇总 + 板块 + 热门藏品 + IP排行）
   │
   ├─ [2] 图表生成 ── charts.py → charts/*.py
   │       ├─ launch_grid: 发行藏品卡片总览（PIL）
   │       ├─ cover: 微信文章封面（PIL）
   │       ├─ market_trend_line: 近7天市值&成交量双轴折线图
   │       ├─ market_overview: 昨日vs前日全市场对比柱状图
   │       ├─ plane_deal_rank: 板块成交量排行横向条形图
   │       ├─ plane_census: 板块涨跌分布堆叠条形图
   │       ├─ top_archives: 分类Top5藏品均价涨跌对比
   │       ├─ ip_distribution: IP发行频次排行
   │       └─ ip_deal_rank: 昨日热门IP成交Top5蝴蝶图
   │
   ├─ [3] AI文章生成 ── llm.py（两阶段）
   │       ├─ 阶段1: 数据核实（temperature=0.1）→ JSON事实
   │       ├─ 阶段2: 文章撰写（temperature=0.2）→ Markdown
   │       └─ 阶段3: 摘要生成（temperature=0.2）→ 一句话
   │
   ├─ [4] 渲染 ── renderer.py
   │       └─ Markdown + 图表标记 → 微信兼容HTML（内联样式）
   │
   └─ [5] 存储 & 发布 ── service.py
           ├─ 存入DB（Article + ArticleImage）
           └─ 发布到微信公众号（wechat_client.py）
```

---

## 二、数据采集详解（analyzer.py）

### 2.1 数据来源

| 数据类型 | 数据源 | 表/接口 | 更新频率 |
|---------|--------|---------|---------|
| 发行日历 | 爬虫 | LaunchCalendar + IP | 每日爬取 |
| 含品详情 | DB | LaunchDetail + JingtanSkuHomepageDetail | 爬取时写入 |
| 含品实时行情 | API | h5/goods/archiveGoods | 实时调用 |
| IP信息 | DB | IP表 | 爬取时写入 |
| 市场日汇总 | 爬虫 | MarketDailySummary | 每日爬取 |
| 板块快照 | 爬虫 | MarketPlaneSnapshot + MarketPlaneCensus | 每日爬取 |
| 藏品排行 | 爬虫 | MarketArchiveSnapshot + MarketTopCensus | 每日爬取 |
| IP市场快照 | 爬虫 | MarketIPSnapshot | 每日爬取 |

### 2.2 关键数据处理逻辑

**含品溢价计算（Python侧预计算，非LLM推算）：**
- 单品溢价率 = (当前地板价 / 发行价 - 1) x 100
- 期望价值 = Σ(概率% x 地板价)
- 期望溢价率 = (期望价值 / 发行价 - 1) x 100

**市场环比计算（Python侧预计算）：**
- market_deal_change_pct = (昨日成交量 - 前日成交量) / 前日成交量 x 100

**IP 发行频次（客观陈述，不做活跃度评级）：**
- 历史总发行次数 + 近一年发行次数（不含今日）

**市场趋势判断：**
- deal_change_pct > +5% → 升温
- deal_change_pct < -5% → 降温
- 其他 → 持平

### 2.3 数据优先级

| 字段 | 优先数据源 | 备选数据源 | 说明 |
|------|-----------|-----------|------|
| 地板价 | live_min_price（实时API） | min_price（DB快照） | 实时API更准确 |
| 在售量 | live_total（实时API） | selling_count（DB快照） | 实时API更准确 |
| 溢价率 | Python预计算值 | — | 禁止LLM自行推算 |
| 成交量环比 | Python预计算值 | — | 禁止LLM自行推算 |

---

## 三、图表生成详解（charts/）

### 3.1 图表类型与数据映射

| 图表键名 | 生成方式 | 数据来源字段 | 输出说明 |
|---------|---------|-------------|---------|
| launch_grid | PIL卡片绘制 | enriched_launches | 每项发行一张卡片，含封面图、价格、含品缩略图 |
| cover | PIL封面绘制 | 标题+摘要统计 | 900x383 微信首图，深蓝渐变背景 |
| ip_distribution | Matplotlib条形图 | ip_distribution | IP发行频次排行 |
| market_trend_line | Matplotlib双轴折线 | summaries_7d | 左轴市值(亿)，右轴成交笔数 |
| market_overview | Matplotlib柱状图 | yesterday + day_before | 昨日vs前日成交对比 |
| plane_deal_rank | Matplotlib横向条形 | top_planes | Top8板块成交量，颜色标注均价涨跌 |
| plane_census | Matplotlib堆叠条形 | plane_census | 板块藏品上涨/下跌/持平分布 |
| top_archives | Matplotlib横向条形 | top_archives | 按分类分组Top5藏品均价涨跌幅 |
| hot_archives_top10 | Matplotlib综合卡片 | hot_archives_top10 | 全局Top10藏品成交量×均价涨跌×地板价 |
| ip_deal_rank | Matplotlib 蝴蝶图 | ip_deep_analysis | 昨日热门IP成交Top5（左成交额、右成交笔数+环比）|

### 3.2 图表样式规范

- 分辨率：DPI 150
- 背景色：#f5f5f5（浅灰）
- 主色：#1677ff（品牌蓝）
- 涨色：#ff4d4f（红）
- 跌色：#52c41a（绿）
- 字体：系统CJK字体（macOS STHeiti / Windows 微软雅黑 / Linux WQY微米黑）

---

## 四、AI文章生成详解（llm.py + prompt.py）

### 4.1 两阶段生成流程

```
原始数据 ──→ 阶段1（数据核实）──→ JSON事实 ──→ 阶段2（文章撰写）──→ Markdown文章
             temperature=0.1              嵌入prompt顶部    temperature=0.2
             只提取、不推断                                  只引用、不推算
```

**为何分两阶段：** LLM在自由写作时容易"自行推算"数字导致错误。阶段1以极低温度提取结构化事实，阶段2强制引用这些已核实的数字，大幅减少数值幻觉。

### 4.2 写作风格控制

**核心原则：** 像券商研报一样客观理性，不像营销号。

**禁止词汇表：**
暴涨、暴跌、狂热、爆发、井喷、疯狂、火爆、震撼、惊人、强势、狂飙、重磅、王炸、逆天、史诗级、现象级

**涨跌幅描述规则：**
| 涨跌幅 | 允许用词 |
|--------|---------|
| < 5% | 小幅上涨/下跌、基本持平 |
| 5% - 20% | 上涨/下跌、明显上涨/下跌 |
| 20% - 50% | 大幅上涨/下跌 |
| > 50% | 显著上涨/下跌 |

**格式禁止：**
- 禁止感叹号、反问句、省略号等修辞手法
- 禁止推荐性用语（不容错过、值得关注、潜力巨大、建议、看好）
- 标题格式：「数藏日报·日期｜核心数据摘要」，纯陈述句

### 4.3 文章四段结构

1. **今日发售日历** — 发行规模概述 + 逐项列出 + 含品实时数据 + launch_grid图
2. **重点藏品解读** — 题材背景 + 发行量稀缺性 + 溢价状态（引用已核实数据）
3. **IP与发行商分析** — 活跃度 + 上次发行 + 昨日市场 + 发行商矩阵
4. **昨日行情复盘** — 全市场成交 + 板块行情 + 热门藏品Top10 + IP排行

---

## 五、图文结合机制

### 5.1 图表插入方式

LLM在Markdown中使用特殊标记插入图表：
```markdown
![描述文本](CHART:chart_key)
```

渲染器（renderer.py）将标记替换为微信兼容的img标签：
```html
<img src="图表URL" style="width:100%;border-radius:8px;margin:16px 0;" />
```

### 5.2 图文一致性保障

| 保障措施 | 说明 |
|---------|------|
| 卡片优先使用实时数据 | launch_grid卡片优先取live_min_price/live_total |
| 图表字段与文本对齐 | 板块图表使用avg_price_rate，与文本引用同一字段 |
| 数据来源标注 | 含品数据标注"实时API"或"历史快照"来源 |
| 图表仅插入已生成的 | prompt中只列出available_charts，未生成的不插入 |

---

## 六、发布流程（service.py + wechat_client.py）

```
generate_article()                          publish_article()
├─ 获取分析数据                               ├─ 上传图片到微信服务器
├─ 生成图表 → 保存本地                         │   ├─ 封面 → upload_material → media_id
├─ AI生成Markdown                             │   └─ 文章图 → upload_image → URL
├─ Markdown → HTML                           ├─ 用微信URL重新渲染HTML
├─ 保存Article(status=draft)                  ├─ 创建草稿 → wechat_media_id
└─ 保存ArticleImage记录                       ├─ 发布 → wechat_publish_id
                                             └─ 更新Article(status=published)
```

**状态流转：** generating → draft → publishing → published（或 failed）

---

## 七、质量保障清单

### 7.1 数据准确性
- [x] 所有数值由Python侧预计算，禁止LLM自行推算
- [x] 两阶段LLM生成：先核实事实JSON，再引用写作
- [x] 图表字段名与数据字典严格对齐（avg_price_rate）
- [x] 实时API数据优先于DB历史快照
- [x] 含品数据标注来源（实时API vs 历史快照）
- [x] API调用失败时回退DB数据，不编造

### 7.2 内容质量
- [x] 禁止夸张词汇表（17个词明确禁止）
- [x] 涨跌幅描述须与数据幅度匹配（4级对应）
- [x] 禁止感叹号/反问句/省略号修辞
- [x] 禁止推荐性用语
- [x] 文物/字画类藏品须结合历史文化背景
- [x] 写作温度0.2（低创造性，高准确性）

### 7.3 图文一致性
- [x] 卡片图和文本使用同源数据（live_min_price优先）
- [x] 图表颜色语义一致（红涨绿跌）
- [x] 图表仅在数据存在时生成
- [x] 文章仅引用已生成的图表

---

## 八、文件索引

| 文件 | 职责 | 关键函数 |
|------|------|---------|
| `service.py` | 生成+发布编排 | generate_article(), publish_article() |
| `llm.py` | LLM调用 | generate_article_content(), _phase1_extract_facts() |
| `renderer.py` | HTML渲染 | markdown_to_wechat_html() |
| `reports/daily/analyzer.py` | 数据采集 | get_daily_data(), get_market_snapshot_data() |
| `reports/daily/prompt.py` | Prompt构建 | build_analysis_prompt(), build_daily_prompt() |
| `reports/daily/charts.py` | 图表编排 | generate_daily_charts() |
| `charts/base.py` | 图表配置 | Matplotlib设置、颜色、字体 |
| `charts/cards.py` | 卡片生成 | generate_launch_grid() |
| `charts/cover.py` | 封面生成 | generate_cover() |
| `charts/market.py` | 行情图表 | chart_market_trend_line(), chart_plane_deal_rank() 等 |
| `charts/ranking.py` | 排行图表 | chart_ip_ranking() |
| `wechat_client.py` | 微信API | upload_image(), create_draft(), publish() |

---

## 九、常见问题排查

| 问题 | 排查方向 |
|------|---------|
| 文章数字与实际不符 | 检查_verified_facts JSON是否正确提取；检查Python预计算值 |
| 图表数据为0或缺失 | 检查MarketDailySummary/MarketPlaneSnapshot等表当日数据是否已爬取 |
| 含品地板价显示0 | 检查archiveGoods API是否返回200；检查archive_id是否正确 |
| 文章语气仍然夸张 | 检查SYSTEM_PROMPT禁止词汇表；确认temperature=0.2 |
| 图表未出现在文章中 | 检查generate_daily_charts返回的keys是否传给available_charts |
| 微信发布失败 | 检查access_token是否过期；检查图片是否上传成功 |
