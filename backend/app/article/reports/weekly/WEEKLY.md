## 周报文章生成规范

周报在**周日晚上**生成，**周一早上**手动发布到微信公众号。

数据统计口径：本自然周（周一 00:00 ~ 周日 23:59，北京时间）。
`get_weekly_data(end_date)` 中 `end_date` 默认为今日（周日），自动推算本周周一为起点。

---

### 一、本周发行日历

数据来源：`launch_calendar` 表（`platform_id = 741`，即鲸探平台）

#### 统计字段
- 发行项数、总发行量（份）、总发行价值（元）
- 均价、最高价、最低价
- 每日发行分布（`daily_trend`）
- IP 发行项数排行

#### 图表
- `launch_grid` — 本周所有发行项封面卡片（封面、IP、价格、数量），`generate_launch_grid`
- `three_week_compare` — 三周发行规模对比（发行项数 + 总价值），`chart_three_week_compare`
- `ip_ranking` — 本周 IP 发行项数排行，`chart_ip_ranking`

#### 对比维度
- 与上周发行项数、总价值、均价的周环比（Python 预计算，字段：`launches_pct`, `value_pct`, `supply_pct`）
- 三周纵向趋势（本周 / 上周 / 上上周，字段：`prev_week`, `prev2_week`）

---

### 二、本周行情分析

数据来源：
- `market_daily_summaries` — 每日全市场汇总（成交量/额/市值）
- `market_plane_snapshots` — 板块每日快照，周内聚合成交量
- `market_archive_snapshots` — 藏品每日排名快照，周内聚合成交量
- `market_top_census` — 行情分类（鲸探50/禁出195）每日市值
- `market_ip_snapshots` — IP 每日排名快照，周内聚合成交量

#### 统计字段
- 全市场累计成交量、成交额（周汇总，`market_week.total_deal_count/total_deal_amount`）
- 全市场总市值（取周末最后一天，`market_week.last_market_value`）
- 每日成交趋势（`market_week.daily`）
- 核心板块每日市值（鲸探50/禁出195，`week_core_plane_values`）
- 板块累计成交 Top8（`week_top_planes`）
- 热门藏品累计成交 Top10（`week_hot_archives`）
- 热门 IP 累计成交 Top10（`ip_market_weekly`）

#### 图表
- `market_daily_trend` — 本周每日成交量趋势（与上周均线对比），`chart_market_daily_trend`
- `core_plane_market_line` — 鲸探50/禁出195 本周每日市值折线，`chart_core_plane_market_line`
- `plane_deal_rank` — 本周板块累计成交量横向排行，`chart_plane_deal_rank`
- `hot_archives_top10` — 本周成交 Top10 藏品，`chart_hot_archives_top10`
- `ip_market_ranking` — 本周 vs 上周 IP 市场成交排行，`chart_ip_market_ranking`
- `ip_deal_rank` — Top5 IP 成交蝴蝶图（成交量/市值），`chart_ip_deal_rank`

#### 对比维度
- 与上周成交量/额的周环比（`market_deal_pct`, `market_amount_pct`）
- 三周成交趋势方向判断

---

### 三、文章结构模板

```
# 数藏周报·MM/DD-MM/DD｜核心摘要（≤21字）

[开篇：2句，直接点明本周发行规模 + 行情核心数据]

## 本周发行日历
![本周发行总览](CHART:launch_grid)
[发行规模三周对比 + 均价对比上周]
![三周发行对比](CHART:three_week_compare)
[IP 发行格局]
![IP 发行排行](CHART:ip_ranking)

## 本周行情复盘

### 全市场成交概况
[成交量/额 vs 上周，周环比，三周趋势方向]
![本周市场日成交趋势](CHART:market_daily_trend)

### 核心藏品市值
[鲸探50/禁出195 本周每日市值走势分析]
![核心藏品市值走势](CHART:core_plane_market_line)

### 板块行情
[板块累计成交排行前3-5名简析]
![板块成交排行](CHART:plane_deal_rank)

### 热门藏品 Top10
[本周累计成交 Top10，按分类简析]
![热门藏品Top10](CHART:hot_archives_top10)

### 热门 IP 市场表现
[本周 IP 成交排行，与上周对比]
![IP 市场成交排行](CHART:ip_market_ranking)
![IP成交Top5](CHART:ip_deal_rank)

## 本周小结
[一段话：发行端特征 + 行情端特征；对下周中性展望]

> 数据截止 YYYY-MM-DD，内容仅供参考，不构成投资建议。
```

---

### 四、写作规范（继承日报）

- 所有数字来自 prompt 数据，环比使用 Python 预计算值，不得自行推算
- 语言克制客观，禁止营销号风格，全文陈述句
- 涨跌描述与幅度匹配：<5% = 小幅，5-20% = 明显，>20% = 大幅，>50% = 显著
- 禁止使用"暴涨""暴跌""不容错过""看好"等夸张/推荐性用语
- 无数据时注明"暂无数据"，不得编造，不得推断
