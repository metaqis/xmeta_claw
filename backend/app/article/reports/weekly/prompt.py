"""周报 Prompt 构建。"""


def _fmt_pct(v) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def build_weekly_prompt(data: dict, available_charts: list[str]) -> str:
    # ── 工具函数 ──────────────────────────────────────────────────────────────
    def chart(key: str, alt: str) -> str:
        """只有图表在 available_charts 中才插入标记，否则返回空字符串。"""
        return f"![{alt}](CHART:{key})" if key in available_charts else ""

    # ── 三周发行对比表 ────────────────────────────────────────────────────────
    pw  = data.get("prev_week") or {}
    p2w = data.get("prev2_week") or {}
    three_week_table = (
        "| 指标 | 本周 | 上周 | 上上周 |\n"
        "|------|------|------|--------|\n"
        f"| 发行项数 | **{data['total_launches']}** | {pw.get('total_launches','N/A')} | {p2w.get('total_launches','N/A')} |\n"
        f"| 总发行量（份） | **{data['total_supply']:,}** | {pw.get('total_supply',0):,} | {p2w.get('total_supply',0):,} |\n"
        f"| 总发行价值（万） | **{data['total_value']/10000:.1f}** | {pw.get('total_value',0)/10000:.1f} | {p2w.get('total_value',0)/10000:.1f} |\n"
        f"| 均价（元） | **{data['avg_price']:.2f}** | {pw.get('avg_price',0):.2f} | {p2w.get('avg_price',0):.2f} |\n"
        f"| 发行数周环比 | **{_fmt_pct(data.get('launches_pct'))}** | — | — |\n"
        f"| 价值周环比 | **{_fmt_pct(data.get('value_pct'))}** | — | — |\n"
    )

    # ── IP 发行排行表（本周 vs 上周） ─────────────────────────────────────────
    prev_ip_map = {x["name"]: x["count"] for x in pw.get("ip_ranking", [])}
    ip_table = "| # | IP名称 | 本周发行 | 上周发行 | 变化 |\n|---|--------|----------|----------|------|\n"
    for i, ip in enumerate(data.get("ip_ranking", [])[:10], 1):
        prev = prev_ip_map.get(ip["name"], 0)
        chg = ip["count"] - prev
        chg_str = f"{'+' if chg >= 0 else ''}{chg}"
        ip_table += f"| {i} | {ip['name']} | {ip['count']} | {prev if prev else '—'} | {chg_str} |\n"

    # ── 每日发行趋势 ──────────────────────────────────────────────────────────
    trend_table = "| 日期 | 发行项数 | 发行价值（万） |\n|------|----------|---------------|\n"
    for d in data.get("daily_trend", []):
        trend_table += f"| {d['date']} | {d['count']} | {d['value']/10000:.1f} |\n"

    # ── 市场行情数据 ──────────────────────────────────────────────────────────
    mw   = data.get("market_week") or {}
    mpw  = data.get("market_prev_week") or {}
    mp2w = data.get("market_prev2_week") or {}

    market_section = ""
    if mw.get("has_data"):
        # 上上周→上周环比
        deal_prev2_pct = "N/A"
        if mpw.get("has_data") and mp2w.get("has_data") and mp2w.get("total_deal_count", 0) > 0:
            val = round((mpw["total_deal_count"] - mp2w["total_deal_count"])
                        / mp2w["total_deal_count"] * 100, 1)
            deal_prev2_pct = _fmt_pct(val)

        market_compare = (
            "| 指标 | 本周 | 上周 | 上上周 |\n"
            "|------|------|------|--------|\n"
            f"| 累计成交量（笔） | **{mw['total_deal_count']:,}** "
            f"| {mpw.get('total_deal_count',0):,} "
            f"| {mp2w.get('total_deal_count',0) if mp2w.get('has_data') else 'N/A'} |\n"
            f"| 累计成交额（万） | **{mw['total_deal_amount']/10000:.1f}** "
            f"| {mpw.get('total_deal_amount',0)/10000:.1f} "
            f"| {mp2w.get('total_deal_amount',0)/10000:.1f if mp2w.get('has_data') else 'N/A'} |\n"
            f"| 成交量周环比 | **{_fmt_pct(data.get('market_deal_pct'))}** | {deal_prev2_pct} | — |\n"
        )

        daily_table = "| 日期 | 成交量（笔） | 成交额（万） | 总市值（亿） |\n|------|------------|------------|-------------|\n"
        for d in mw.get("daily", []):
            mv = f"{d['market_value']/1e8:.2f}" if d.get("market_value") else "—"
            amt = f"{d['deal_amount']/10000:.1f}" if d.get("deal_amount") else "—"
            daily_table += f"| {d['date']} | {d.get('deal_count',0):,} | {amt} | {mv} |\n"

        market_section = f"""
## 本周行情数据（二级市场快照）

### 三周成交量对比
{market_compare}
（预计算周环比可直接引用，无需自行计算）

### 本周每日成交趋势
{daily_table}
{chart("market_daily_trend", "本周市场日成交趋势")}
"""
    else:
        market_section = "\n## 本周行情数据\n（本周暂无市场快照数据，行情分析节跳过）\n"

    # ── IP 市场成交排行数据 ───────────────────────────────────────────────────
    prev_ip_market_map = {x["name"]: x["week_deal_count"] for x in data.get("prev_ip_market_weekly", [])}
    ip_market_section = ""
    if data.get("ip_market_weekly"):
        ip_market_table = "| # | IP名称 | 本周成交量 | 上周成交量 | 变化 | 均价（元） |\n|---|--------|------------|------------|------|----------|\n"
        for i, ip in enumerate(data["ip_market_weekly"][:10], 1):
            prev = prev_ip_market_map.get(ip["name"], 0)
            chg  = ip["week_deal_count"] - prev
            avg  = f"¥{ip['avg_price']:.2f}" if ip.get("avg_price") else "—"
            ip_market_table += (
                f"| {i} | {ip['name']} | {ip['week_deal_count']:,} "
                f"| {prev:,} | {'+' if chg >= 0 else ''}{chg:,} | {avg} |\n"
            )
        ip_market_section = f"""
### 本周 IP 市场成交排行（累计成交量）
{ip_market_table}
{chart("ip_market_ranking", "本周 vs 上周 IP 市场成交量")}
"""

    # ── 新增藏品 ──────────────────────────────────────────────────────────────
    archives_info = ""
    for a in data.get("new_archives", [])[:10]:
        archives_info += f"- {a['name']}（IP：{a['ip']}，数量：{a['goods_count'] or '未知'}）\n"

    return f"""请为以下数据撰写一篇**数藏周报**微信公众号文章。

---
## 本周发行概览（{data['start_date']} ~ {data['end_date']}）

### 三周发行对比
{three_week_table}
（所有环比值为 Python 预计算结果，写作时直接引用，不得自行推算）

### 本周 IP 发行排行
{ip_table}

### 本周每日发行趋势
{trend_table}
{market_section}
{ip_market_section}
### 本周新增藏品
{archives_info or '（无新增藏品）'}

---
## 可用图表
{', '.join(available_charts)}

图表插入规则：
- `three_week_compare` → 三周对比分析段落后
- `daily_trend` + `value_trend` → 每日趋势分析段落后
- `ip_ranking` → IP 发行分析段落后
- `market_daily_trend` → 行情成交趋势分析后
- `ip_market_ranking` → IP 市场成交分析后

---
**重要：文章标题（第一行 `# 标题`）格式为「数藏周报·MM/DD-MM/DD｜核心摘要」，总长度必须 ≤ 32 字（含标点）。**
**正确示例：`# 数藏周报·04/14-04/20｜58款·¥1,240万`（共24字 ✓）**

请撰写一篇 **1200-2000 字** 的数藏周报文章，按以下结构组织，**每节分析后紧跟对应图表**：

```
# 数藏周报·MM/DD-MM/DD｜[核心数据摘要，≤15字]

[1-2 句开篇：直接给出本周发行规模 + 与上周的核心对比，不做铺垫]

## 本周发行总结

[三周纵向对比分析：
  - 发行项数、总量、总价值的周环比（直接引用 launches_pct/value_pct，不重算）
  - 与上上周相比的中期趋势判断（2-3 周的方向性）
  - 涨跌描述须与数据幅度匹配：<5%=小幅，5-20%=明显，>20%=大幅]
![三周发行对比](CHART:three_week_compare)

[每日发行节奏分析：结合趋势表，指出高峰日/低谷日及可能原因]
![日发行数量趋势](CHART:daily_trend)
![发行价值趋势](CHART:value_trend)

[IP 发行格局：哪些 IP 本周活跃度上升/下降，与上周对比]
![IP 发行排行](CHART:ip_ranking)

## 本周行情分析
（若无市场快照数据则删除本节）

[本周市场概况：
  - 累计成交量 vs 上周（引用 market_deal_pct），vs 上上周形成趋势判断
  - 日成交节奏：高峰/低谷日，是否与发行节奏相关联]
![本周市场日成交趋势](CHART:market_daily_trend)

[IP 市场表现：
  - 哪些 IP 本周市场最活跃，与上周对比有何变化
  - 发行活跃 IP 与市场成交 IP 是否一致，若不一致则分析原因]
![IP 市场成交排行](CHART:ip_market_ranking)

## 总结
[简短结论：本周整体特征（发行端 + 行情端各一句）；
 对下周的中性展望，不做价格预测或投资建议]
```

**写作规范：**
- 所有数值来自 prompt 数据，环比变化率使用预计算值，不得自行推算
- 语言克制客观，禁止营销号风格；全文使用陈述句
- 涨跌描述须与数据幅度匹配，不得用"暴涨""暴跌"等夸张词
- 图表标记必须紧跟对应分析段落，不得集中堆在文末"""
