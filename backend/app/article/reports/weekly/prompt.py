"""周报 Prompt 构建。

两段式结构：
  §1 本周发行日历 — 发行规模 + 三周对比 + IP 格局
  §2 本周行情复盘 — 市场成交趋势 + 核心板块市值 + 板块/藏品/IP 排行
"""


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _fmt_pct(v) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _fmt_wan(n, unit: str = "") -> str:
    """≥10000 显示为「X.XX万」，否则原样显示。"""
    if n is None:
        return "—"
    n = float(n)
    if abs(n) >= 10000:
        s = f"{n / 10000:.2f}".rstrip("0").rstrip(".")
        return f"{s}万{unit}"
    return f"{n:,.0f}{unit}"


def _fmt_rate(v) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


# ── 数据块构建 ────────────────────────────────────────────────────────────────

def _build_launch_section(data: dict) -> str:
    """构建「本周发行日历」数据块。"""
    pw  = data.get("prev_week") or {}
    p2w = data.get("prev2_week") or {}

    # 三周发行对比表
    three_week = (
        "| 指标 | 本周 | 上周 | 上上周 |\n"
        "|------|------|------|--------|\n"
        f"| 发行项数 | **{data['total_launches']}** | {pw.get('total_launches', 'N/A')} | {p2w.get('total_launches', 'N/A')} |\n"
        f"| 总发行量（份） | **{data['total_supply']:,}** | {pw.get('total_supply', 0):,} | {p2w.get('total_supply', 0):,} |\n"
        f"| 总发行价值（万） | **{_fmt_wan(data['total_value'])}** | {_fmt_wan(pw.get('total_value', 0))} | {_fmt_wan(p2w.get('total_value', 0))} |\n"
        f"| 均价（元） | **¥{data['avg_price']:.2f}** | ¥{pw.get('avg_price', 0):.2f} | ¥{p2w.get('avg_price', 0):.2f} |\n"
        f"| 发行项数周环比 | **{_fmt_pct(data.get('launches_pct'))}** | — | — |\n"
        f"| 发行价值周环比 | **{_fmt_pct(data.get('value_pct'))}** | — | — |\n"
        f"| 均价周环比 | **{_fmt_pct(data.get('avg_price_pct'))}** | — | — |\n"
        "\n（所有环比值为 Python 预计算结果，直接引用，不得自行推算）"
    )

    # 本周发行明细（按日期分组）
    launches = data.get("launches") or []
    by_date: dict[str, list] = {}
    for l in launches:
        d = l["sell_time"][:10]
        by_date.setdefault(d, []).append(l)

    daily_list = ""
    for d in sorted(by_date):
        items = by_date[d]
        daily_list += f"\n**{d}**（{len(items)} 项）\n"
        for l in items:
            prio = f"，含优先购 {l['priority_purchase_num']:,} 份" if l["is_priority_purchase"] else ""
            daily_list += (
                f"- {l['name']}（IP：{l['ip_name']}）"
                f"｜¥{l['price']:.2f}｜{l['count']:,} 份｜总价值 {_fmt_wan(l['value'])}{prio}\n"
            )

    # IP 发行排行（本周 vs 上周）
    prev_ip_map = {x["name"]: x["count"] for x in pw.get("ip_ranking", [])}
    ip_table = (
        "| # | IP名称 | 本周发行项数 | 上周发行项数 | 变化 |\n"
        "|---|--------|------------|------------|------|\n"
    )
    for i, ip in enumerate(data.get("ip_ranking", [])[:10], 1):
        prev = prev_ip_map.get(ip["name"], 0)
        chg = ip["count"] - prev
        ip_table += f"| {i} | {ip['name']} | {ip['count']} | {prev or '—'} | {'+' if chg >= 0 else ''}{chg} |\n"

    return f"""## 本周发行数据（{data['start_date']} ~ {data['end_date']}）

### 三周发行规模对比
{three_week}

### 本周发行明细（按日期）
{daily_list or '（暂无发行数据）'}

### IP 发行项数排行
{ip_table}"""


def _build_market_section(data: dict) -> str:
    """构建「本周行情复盘」数据块。"""
    mw   = data.get("market_week") or {}
    mpw  = data.get("market_prev_week") or {}
    mp2w = data.get("market_prev2_week") or {}

    if not mw.get("has_data"):
        return "## 本周行情数据\n（本周暂无市场快照数据，行情分析节跳过）"

    # 三周成交对比
    def _cnt(d): return d.get("total_deal_count", 0) if d.get("has_data") else "N/A"
    def _amt(d):
        v = d.get("total_deal_amount")
        return _fmt_wan(v) if d.get("has_data") and v else "N/A"

    market_compare = (
        "| 指标 | 本周 | 上周 | 上上周 |\n"
        "|------|------|------|--------|\n"
        f"| 累计成交量（笔） | **{mw['total_deal_count']:,}** | {_cnt(mpw):,} | {_cnt(mp2w)} |\n"
        f"| 累计成交额 | **{_fmt_wan(mw['total_deal_amount'])}** | {_amt(mpw)} | {_amt(mp2w)} |\n"
        f"| 成交量周环比 | **{_fmt_pct(data.get('market_deal_pct'))}** | — | — |\n"
        f"| 成交额周环比 | **{_fmt_pct(data.get('market_amount_pct'))}** | — | — |\n"
        "\n（所有环比值为 Python 预计算结果，直接引用，不得自行推算）"
    )

    # 每日成交明细
    daily_table = "| 日期 | 成交量（笔） | 成交额 | 总市值 |\n|------|-----------|--------|--------|\n"
    for d in mw.get("daily", []):
        mv = f"¥{d['market_value'] / 1e8:.2f}亿" if d.get("market_value") else "—"
        amt = _fmt_wan(d.get("deal_amount"))
        daily_table += f"| {d['date']} | {d.get('deal_count', 0):,} | {amt} | {mv} |\n"

    # 核心板块每日市值
    core_values = data.get("week_core_plane_values") or []
    core_table = ""
    if core_values:
        core_table = (
            "\n### 核心板块（鲸探50/禁出195）本周每日市值\n"
            "| 日期 | 鲸探50 | 禁出195 |\n"
            "|------|--------|--------|\n"
        )
        for s in core_values:
            j = f"¥{s['jingtan50_market_value'] / 1e8:.2f}亿" if s.get("jingtan50_market_value") is not None else "—"
            r = f"¥{s['restricted_relics_market_value'] / 1e8:.2f}亿" if s.get("restricted_relics_market_value") is not None else "—"
            core_table += f"| {s['stat_date']} | {j} | {r} |\n"

    # 本周板块累计成交排行
    planes = data.get("week_top_planes") or []
    plane_table = ""
    if planes:
        plane_table = (
            "\n### 本周板块累计成交排行（Top 8）\n"
            "| # | 板块 | 周累计成交量 |\n"
            "|---|------|------------|\n"
        )
        for i, p in enumerate(planes, 1):
            plane_table += f"| {i} | {p['plane_name']} | {p['deal_count']:,} |\n"

    # 本周热门藏品 Top10
    archives = data.get("week_hot_archives") or []
    archive_table = ""
    if archives:
        archive_table = (
            "\n### 本周成交量 Top10 藏品\n"
            "| # | 藏品 | 分类 | 周累计成交 | 均价 | 最低价 |\n"
            "|---|------|------|----------|------|-------|\n"
        )
        for i, a in enumerate(archives, 1):
            avg = f"¥{a['avg_amount']:.2f}" if a.get("avg_amount") else "—"
            mn  = f"¥{a['min_amount']:.2f}" if a.get("min_amount") else "—"
            archive_table += f"| {i} | {a['archive_name']} | {a.get('top_name', '—')} | {a['deal_count']:,} | {avg} | {mn} |\n"

    # IP 市场成交排行（本周 vs 上周）
    prev_ip_map = {x["name"]: x["week_deal_count"] for x in data.get("prev_ip_market_weekly", [])}
    ip_market = data.get("ip_market_weekly") or []
    ip_market_table = ""
    if ip_market:
        ip_market_table = (
            "\n### 本周 IP 市场成交排行（累计成交量）\n"
            "| # | IP名称 | 本周成交量 | 上周成交量 | 变化 | 均价 |\n"
            "|---|--------|----------|----------|------|------|\n"
        )
        for i, ip in enumerate(ip_market[:10], 1):
            prev = prev_ip_map.get(ip["name"], 0)
            chg  = ip["week_deal_count"] - prev
            avg  = f"¥{ip['avg_price']:.2f}" if ip.get("avg_price") else "—"
            ip_market_table += (
                f"| {i} | {ip['name']} | {ip['week_deal_count']:,} "
                f"| {prev:,} | {'+' if chg >= 0 else ''}{chg:,} | {avg} |\n"
            )

    return f"""## 本周行情数据（二级市场快照）

### 三周成交对比
{market_compare}

### 本周每日成交明细
{daily_table}
{core_table}{plane_table}{archive_table}{ip_market_table}"""


# ── 主函数 ────────────────────────────────────────────────────────────────────

def build_weekly_prompt(data: dict, available_charts: list[str]) -> str:
    """构建周报文章撰写 Prompt。"""

    def _chart(key: str, alt: str) -> str:
        return f"![{alt}](CHART:{key})" if key in available_charts else ""

    launch_section = _build_launch_section(data)
    market_section = _build_market_section(data)

    return f"""请为以下数据撰写一篇**数藏周报**微信公众号文章。

---
{launch_section}

---
{market_section}

---
## 可用图表
{', '.join(available_charts)}

---
## 撰写要求

**标题格式**（第一行）：`# 数藏周报·MM/DD-MM/DD｜核心摘要`
- 总长度 ≤ 32 字；核心摘要 ≤ 15 字，只写最核心一组数据，禁止感叹号/问号
- 正确示例：`# 数藏周报·04/14-04/20｜58款·¥1,240万`

请撰写 **1200-2000 字**，按以下两段结构组织，每节分析后紧跟对应图表：

```
# 数藏周报·[MM/DD-MM/DD]｜[核心摘要≤15字]

[开篇2句：直接点明本周发行规模 + 行情核心成交数据，无铺垫]

## 本周发行日历
{_chart("launch_grid", "本周发行总览")}
[发行规模三周对比：
 - 发行项数、总价值、均价的周环比（直接使用预计算值 launches_pct/value_pct/avg_price_pct）
 - 与上上周三周趋势方向（方向性判断，如"连续两周回升"）
 - 涨跌描述须与幅度匹配：<5%=小幅，5-20%=明显，>20%=大幅]
{_chart("three_week_compare", "三周发行对比")}

[本周每日发行节奏：结合明细，指出高峰日 + 各日价格特征]

[IP 发行格局：哪些 IP 本周发行项数最多；与上周相比活跃度有何变化]
{_chart("ip_ranking", "IP 发行排行")}

## 本周行情复盘
（若无市场快照数据则删除本节）

### 全市场成交概况
[本周累计成交量/额 vs 上周（引用 market_deal_pct/market_amount_pct）；
 三周趋势方向；成交量最高的单日及可能原因]
{_chart("market_daily_trend", "本周市场日成交趋势")}

### 核心藏品市值
[若 week_core_plane_values 有数据：分析鲸探50/禁出195本周每日市值走势，
 周内最高/最低点，与发行节奏或市场情绪的关联（客观陈述，不做预测）]
{_chart("core_plane_market_line", "核心藏品市值走势")}

### 板块行情
[板块累计成交排行前3-5名简析（只陈述排名和数量，不做溢价/潜力判断）]
{_chart("plane_deal_rank", "板块成交排行")}

### 热门藏品 Top10
[本周累计成交 Top10：逐一列出名称、分类、成交量；
 对排名靠前藏品的均价和地板价做客观陈述；
 若同一分类多个藏品上榜则合并说明]
{_chart("hot_archives_top10", "热门藏品Top10")}

### 热门 IP 市场表现
[本周 IP 成交排行：逐一陈述排名 + IP + 成交量 + 与上周对比；
 Top5 合计成交占全市场比例（Top5合计/market_week.total_deal_count × 100%）；
 若 ip_market_weekly 为空则删除本节]
{_chart("ip_market_ranking", "IP 市场成交排行")}
{_chart("ip_deal_rank", "IP成交Top5")}

## 本周小结
[3-5句：发行端一句特征总结 + 行情端一句趋势总结；
 对下周的中性客观展望（只陈述预期，不做价格预测或投资建议）]

> 数据截止 {data['end_date']}，市场价格实时变动，内容仅供参考，不构成投资建议。
```

**写作红线（违反则文章不合格）**：
- 所有数字来自 prompt 数据，环比使用预计算值，不得自行推算
- 全文陈述句，禁止感叹号/问号/省略号，禁止营销号风格
- 禁止"暴涨""暴跌""不容错过""看好""建议"等夸张/推荐性用语
- 涨跌描述必须与幅度匹配（<5% 用"小幅"，5-20% 用"明显"，>20% 用"大幅"）
- 无数据时注明"暂无数据"，不得编造
- **严禁在正文中出现任何英文字段名**（如 `launches_pct`、`market_deal_pct` 等）"""

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
