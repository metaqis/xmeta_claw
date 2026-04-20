"""日报 Prompt 构建 + 系统提示词。

两阶段生成流程：
  阶段1 — 数据核实（ANALYSIS_SYSTEM_PROMPT + build_analysis_prompt）
           → 让 LLM 以极低温度从原始数据提取 JSON 事实，预计算溢价率等指标
  阶段2 — 文章撰写（SYSTEM_PROMPT + build_daily_prompt）
           → 将阶段1核实的 JSON 事实嵌入 prompt，严格要求只用已核实数字
"""

# ── 阶段1：数据核实系统提示词 ─────────────────────────────────────────────
ANALYSIS_SYSTEM_PROMPT = """你是一位严谨的数字藏品行业数据核实专员。

你的职责是从提供的原始数据中提取并核实关键事实，以结构化 JSON 输出。

严格规则：
1. 只输出数据中直接存在的事实，不得推断或臆造任何不在数据中的内容
2. 数值变化率（如日环比%）优先使用原始数据中已标注的「预计算值」，不得自行重算
3. 含品溢价计算公式：溢价% = (当前最低价 / 成本估值 - 1) × 100，使用原始数据中算式
4. 若某字段数据缺失、为 0 或为 null，对应字段输出 null，不得填入猜测值
5. IP活跃度等级判断依据：近30天发行 ≥ 3次=密集，1-2次=适中，0次=稀缺
6. 市场趋势判断依据（使用预计算成交量日环比）：
   - deal_change_pct > +5%  → market_trend = "升温"
   - deal_change_pct < -5%  → market_trend = "降温"
   - -5% ≤ deal_change_pct ≤ +5% 或无数据 → market_trend = "持平"
7. 只输出 JSON，不输出任何解释性前缀或后缀"""

# ── 阶段2：文章撰写系统提示词 ─────────────────────────────────────────────
SYSTEM_PROMPT = """你是一位专业的数字藏品行业分析师，擅长撰写微信公众号数据分析文章。
你具备中国历史文化、艺术品鉴赏的背景知识，能对文物字画类藏品进行客观的背景解读。

## 数据使用规则（最高优先级）
1. **若 prompt 中包含「已核实数据事实」JSON，所有数字必须来自该 JSON，不得使用其他来源的数字**
2. **严禁编造、推算、夸大任何数字或结论；含品溢价率、环比变化等必须使用预计算值**
3. 若某数据不存在或为 null，直接说"暂无数据"，不得替换为猜测值
4. 对市场趋势的判断（升温/降温等）必须对应数据中的成交量变化，不得夸大幅度
5. **严禁使用以下词汇或类似夸张表述**："暴涨""暴跌""狂热""爆发""井喷""疯狂""火爆""震撼""惊人""强势""狂飙""重磅""王炸""逆天""史诗级""现象级"
6. **涨跌描述须严格对应数据幅度**：
   - 涨跌幅 <5%：用"小幅上涨/下跌"或"基本持平"
   - 涨跌幅 5%-20%：用"上涨/下跌"或"明显上涨/下跌"
   - 涨跌幅 20%-50%：用"大幅上涨/下跌"
   - 涨跌幅 >50%：才可用"显著上涨/下跌"
7. **不得使用反问句、感叹句来制造夸张效果**，全文使用陈述句

## 文化背景分析要求
- 藏品题材为**文物/字画/历史人物/传统文化**时，须结合该文物/作品的历史背景、艺术价值或文化意义做客观介绍，不能仅列举价格和数量
- 藏品题材为**联名/现代IP**时，需简介该 IP 的品牌背景和受众定位
- 以上背景介绍须保持客观，**禁止使用"不容错过""值得期待""潜力巨大"等主观推荐性用语**

## 写作风格（关键）
1. **克制、专业、数据驱动**：像券商研报一样客观理性，不像营销号
2. 文章结构清晰，使用 Markdown 格式输出
3. 分析有依据，结合行业背景给出见解，见解必须有数据支撑
4. 语言简洁专业，适合数藏爱好者和投资者阅读
5. 善用对比、趋势、排行等维度增强分析价值，幅度描述须与数据匹配
6. **直接陈述事实和数据，不做情绪渲染，不做投资暗示**

## 微信公众号格式规范
- 文章标题（第一行 `# 标题`）：简洁概括当日核心数据，格式为「数藏日报·日期｜核心数据摘要」，**标题不得超过64个字符（含标点符号和空格）**，**禁止使用问号、感叹号、省略号等修辞手法**
- 一级章节用 `## 一级标题`，二级用 `### 二级标题`
- 开头 1-2 句直接点明当日发行核心数据（发行项数、总量、总价值），不做铺垫
- 关键数字和结论用 `**加粗**` 标注
- 每个主要章节后插入对应图表（使用下方标记格式）
- 适当使用项目符号列表（`-`）呈现多维度数据
- 文末加简短数据声明：> 数据截止 XX，市场价格实时变动，内容仅供参考，不构成投资建议。

## 可用图表标记
- `![发行藏品总览](CHART:launch_grid)` — 当日发行藏品封面卡片图
- `![IP排行](CHART:ip_ranking)` / `![IP分布](CHART:ip_distribution)` — IP排行/分布图
- `![月度各周概况](CHART:weekly_breakdown)` — 月度各周分组图
- `![市场概览](CHART:market_overview)` — 昨日 vs 前日全市场成交对比柱状图
- `![板块成交排行](CHART:plane_deal_rank)` — Top 8 板块成交量横向条形图（附均价涨跌颜色）
- `![板块涨跌分布](CHART:plane_census)` — 板块藏品上涨/下跌/持平堆叠条形图
- `![热门藏品涨跌](CHART:top_archives)` — 各分类 Top 5 藏品均价涨跌幅对比图
- `![市值成交趋势](CHART:market_trend_line)` — 近7天全市场市值 & 成交量双轴折线图
- `![IP成交排行](CHART:ip_deal_rank)` — 昨日 IP 成交量横向条形排行图

**仅使用 available_charts 中列出的图表键名，未列出则不插入。**"""


# ── 阶段1：数据核实 Prompt ────────────────────────────────────────────────

def build_analysis_prompt(data: dict) -> str:
    """
    构建第一阶段数据核实提示词。

    此阶段要求 LLM 严格从原始数据中提取关键事实（temperature=0.1），
    输出 JSON 供第二阶段文章撰写时作为「已核实事实」引用，减少数值幻觉。

    关键设计：
    - 含品溢价公式以「算式展开」形式写进 prompt，让 LLM 只填入结果，不做额外推理
    - 所有环比变化率使用 Python 侧预计算的值，LLM 无需重算
    - IP 活跃度等级使用固定阈值（近30天≥3次=密集）
    """
    today_cnt = data["total_launches"]

    # 今日发行清单（简洁格式，供LLM核实基本数字；含品类型加入sku_desc摘要以辅助highlight提取）
    launch_list = ""
    for l in data["launches"][:20]:
        prio_flag = "，含优先购" if l["is_priority_purchase"] else ""
        launch_list += (
            f"  - {l['name']}（{l['ip_name']}）：¥{l['price']}，"
            f"{l['count']:,}份，总价值¥{l['value']:,.0f}{prio_flag}\n"
        )
    # 补充含品的 sku_desc 摘要（帮助 LLM 提取 highlight 时有题材背景依据）
    for el in (data.get("enriched_launches") or [])[:10]:
        for ca in (el.get("contain_archives") or []):
            desc = (ca.get("sku_desc") or "").strip()[:120]
            if desc:
                launch_list += f"    └ 【{ca['archive_name']}】简介：{desc}\n"

    # 含品溢价原始数值（展开算式，避免LLM自行推算错误）
    # NOTE: percentage 是抽签概率（= salesNum / 发行总量），不是成本分摊
    # 溢价 = (地板价 / 发行价 - 1) × 100，即买家实际支付 vs 二级市场价
    contain_raw = ""
    for el in (data.get("enriched_launches") or [])[:10]:
        archives = el.get("contain_archives") or []
        price = el.get("price") or 0
        # 先算该发行整体的期望价值 = Σ(概率 × 地板价)
        ev_parts = []
        for ca in archives:
            pct = ca.get("percentage") or 0
            fp = ca.get("live_min_price") or ca.get("min_price") or 0
            if pct and fp:
                ev_parts.append((pct, fp))
        if price and ev_parts:
            ev = sum(p / 100 * fp for p, fp in ev_parts)
            ev_premium = round((ev / price - 1) * 100, 1)
            contain_raw += (
                f"  ▶ 【{el['name']}】发行价¥{price}，"
                f"期望价值=Σ(概率×地板价)=¥{ev:.2f}，"
                f"期望溢价={(ev_premium):+.1f}%"
                f"（{'正EV' if ev_premium > 5 else '负EV' if ev_premium < -5 else '基本持平'}）\n"
            )
        for ca in archives:
            pct = ca.get("percentage") or 0
            min_price = ca.get("live_min_price") or ca.get("min_price") or 0
            live_total = ca.get("live_total")
            data_source = "实时API" if ca.get("live_min_price") else "历史快照"
            if price and min_price:
                # 溢价率 = (地板价 / 发行价 - 1) × 100
                premium_pct = round((min_price / price - 1) * 100, 1)
                live_info = f"，在售 {live_total:,} 件" if live_total is not None else f"，在售{ca.get('selling_count',0)}件"
                assessment = '溢价' if premium_pct > 5 else '破发' if premium_pct < -5 else '基本持平'
                contain_raw += (
                    f"  - 【{ca['archive_name']}】概率{pct}%，发行价¥{price}（数据来源：{data_source}）\n"
                    f"    当前地板价=¥{min_price}{live_info}"
                    f"，成交{ca.get('deal_count',0)}笔\n"
                    f"    溢价=({min_price}/{price}-1)×100={premium_pct}%"
                    f"（{assessment}）\n"
                )

    # IP 活跃度原始数据（便于LLM判断活跃等级）
    ip_activity = ""
    for ipn, ip_data in (data.get("ip_deep_analysis") or {}).items():
        total = ip_data.get("total_launches", 0)
        r30 = ip_data.get("recent_30d_launches", 0)
        fans = ip_data.get("fans_count", 0)
        # 活跃度等级：近30天≥3次=密集；1-2次=适中；0次=稀缺
        level = "密集" if r30 >= 3 else ("适中" if r30 >= 1 else "稀缺")
        ip_activity += (
            f"  - {ipn}：历史发行{total}次，近30天（不含今日）{r30}次 → 活跃度：{level}"
            + (f"，粉丝{fans:,}人" if fans else "") + "\n"
        )
        last = ip_data.get("last_launch")
        if last:
            ip_activity += (
                f"    上次发行：{last['sell_time']}《{last['name']}》"
                f"，¥{last['price']:.2f}，{last['count']:,}份\n"
            )
        snap = (ip_data.get("market_snapshot") or {}).get("yesterday")
        if snap:
            rate = snap.get("deal_count_rate")
            rate_str = f"({'+' if rate and rate >= 0 else ''}{rate:.1f}%)" if rate is not None else ""
            ip_activity += (
                f"    昨日市场：成交{snap.get('deal_count','N/A')}笔{rate_str}"
                f"，市值{snap.get('market_amount','N/A')}\n"
            )
        else:
            ip_activity += "    昨日市场快照：暂无\n"

    # 市场数据（使用Python预计算的环比值，明确标注可直接使用）
    market = data.get("market_analysis") or {}
    market_block = "  （暂无行情数据）\n"
    if market.get("has_data"):
        yd = market.get("yesterday") or {}
        db_ = market.get("day_before") or {}
        change_pct = data.get("market_deal_change_pct")
        change_str = f"{change_pct:+.1f}%" if change_pct is not None else "N/A"
        market_block = (
            f"  昨日总成交：{yd.get('total_deal_count', 'N/A')} 笔\n"
            f"  前日总成交：{db_.get('total_deal_count', 'N/A') if db_ else 'N/A'} 笔\n"
            f"  预计算成交量日环比：{change_str}（Python预计算，可直接使用此值）\n"
            f"  成交额最高板块：{yd.get('top_plane_name', 'N/A')}"
            f"（{yd.get('top_plane_deal_count', 'N/A')} 笔）\n"
        )
        # 附上Top板块数据供LLM核实
        for p in (market.get("top_planes") or [])[:5]:
            market_block += (
                f"  板块「{p['plane_name']}」：成交{p['deal_count']:,}笔"
                f"，均价涨跌幅{p.get('avg_price_rate', 'N/A')}%"
                f"，最新成交价¥{p.get('deal_price', 'N/A')}\n"
            )

    # 热门藏品Top10（昨日全市场成交量，用于核实文章行情部分的数字）
    hot10_block = ""
    hot10 = (market.get("hot_archives_top10") or [])[:10]
    for i, a in enumerate(hot10, 1):
        avg = f"¥{a['avg_amount']:.2f}" if a.get("avg_amount") else "N/A"
        mn = f"¥{a['min_amount']:.2f}" if a.get("min_amount") else "N/A"
        rate = a.get("avg_amount_rate")
        rate_str = f"{rate:+.2f}%" if rate is not None else "N/A"
        hot10_block += (
            f"  {i}. 【{a['archive_name']}】（{a.get('top_name','N/A')}）"
            f"成交{a.get('deal_count','N/A')}笔，均价{avg}（{rate_str}），地板价{mn}\n"
        )

    return f"""请从以下原始数据中核实并提取关键事实，以 JSON 格式输出。

=== 原始数据 ===

【今日发行统计】
  日期：{data['date']}
  今日发行：{today_cnt} 项
  总供应量：{data['total_supply']:,} 份
  总价值：¥{data['total_value']:,.0f}
  均价：¥{data['avg_price']:.2f}（最高¥{data['max_price']:.2f} / 最低¥{data['min_price']:.2f}）

【发行明细（含sku_desc摘要）】
{launch_list or '  （无发行数据）'}
【含品溢价详情（已展开算式，请核实结果数字）】
{contain_raw or '  （暂无含品价格数据）'}
【IP 活跃度数据】
{ip_activity or '  （暂无IP数据）'}
【二级市场行情（昨日快照）】
{market_block}
【昨日成交量全市场 Top10 藏品】
{hot10_block or '  （暂无热门藏品数据）'}
=== 输出要求 ===

严格按以下 JSON 结构输出，所有数字必须与原始数据一致，不得自行推算：

{{
  "date": "{data['date']}",
  "launch_facts": {{
    "total_count": {today_cnt},
    "total_value": {data['total_value']:.0f},
    "avg_price": {data['avg_price']:.2f}
  }},
  "notable_launches": [
    {{
      "name": "<藏品名>",
      "ip": "<IP名>",
      "price": <数字>,
      "count": <数字>,
      "highlight": "<一句话亮点：优先使用sku_desc中的题材背景（文物/IP/艺术家），补充发行量/稀缺性等，只用已有信息>"
    }}
  ],
  "archive_premiums": [
    {{
      "archive_name": "<含品名>",
      "launch_name": "<所属发行名>",
      "percentage": <抽签概率%>,
      "issue_price": <发行价>,
      "current_min_price": <当前地板价（live_min_price优先）>,
      "live_total": <预售/在售总量或null>,
      "premium_pct": <溢价%，使用上方展开算式的结果，即(地板价/发行价-1)×100>,
      "assessment": "<溢价/持平/破发>"
    }}
  ],
  "ip_analysis": [
    {{
      "ip_name": "<IP名>",
      "total_launches": <历史总次数>,
      "recent_30d_launches": <近30天次数>,
      "activity_level": "<密集/适中/稀缺>",
      "fans_count": <粉丝数或null>,
      "today_count": <今日该IP发行项数>,
      "last_launch_time": "<上次发行日期或null>",
      "last_launch_name": "<上次发行名或null>",
      "last_launch_price": <上次发行价或null>,
      "yesterday_deal_count": <昨日成交笔数或null>,
      "yesterday_deal_count_rate": <昨日成交量环比%或null>,
      "yesterday_market_amount": <昨日市值或null>
    }}
  ],
  "market_facts": {{
    "has_data": <true/false>,
    "yesterday_deal_count": <昨日成交笔数，无则null>,
    "day_before_deal_count": <前日成交笔数，无则null>,
    "deal_change_pct": <预计算成交量环比或null>,
    "market_trend": "<升温/降温/持平，依据System规则6判断>",
    "top_plane_name": "<成交量最高板块，无则null>",
    "top_plane_deal_count": <最高板块成交量，无则null>
  }},
  "hot_archives_top10": [
    {{
      "rank": <排名>,
      "archive_name": "<藏品名>",
      "category": "<所属分类>",
      "deal_count": <成交笔数>,
      "avg_amount": <均价或null>,
      "avg_amount_rate": <均价涨跌幅%或null>,
      "min_amount": <地板价或null>
    }}
  ]
}}"""


# ── 阶段2：文章撰写 Prompt ────────────────────────────────────────────────

def build_daily_prompt(data: dict, available_charts: list[str]) -> str:
    """
    构建第二阶段文章撰写提示词。

    若 data 中含有 _verified_facts 键（来自第一阶段核实），
    会将其嵌入 prompt 顶部作为「已核实数据事实」，要求 LLM 优先使用其中的数字。

    注意字段名：
      top_planes[i].avg_price_rate — 均价日涨跌幅 %（不是均价本身）
    """
    market_change_disp = (
        f"{data['market_deal_change_pct']:+.1f}%"
        if data.get("market_deal_change_pct") is not None
        else "N/A（数据不足）"
    )

    # 发行清单表格
    launches_table = ""
    for i, l in enumerate(data["launches"][:30], 1):
        prio = f"优先购{l['priority_purchase_num']:,}份" if l["is_priority_purchase"] else "—"
        launches_table += (
            f"| {i} | {l['name']} | {l['ip_name']} "
            f"| ¥{l['price']:.2f} | {l['count']:,} | ¥{l['value']:,.0f} | {prio} |\n"
        )

    # 含品详情（展示含品的市场数据，是文章中藏品解读的核心依据）
    contain_sections = ""
    for el in (data.get("enriched_launches") or [])[:10]:
        contain = el.get("contain_archives") or []
        assoc   = el.get("association_archives") or []
        if not contain and not assoc:
            continue
        contain_sections += (
            f"\n**▶ {el['name']}**（{el['sell_time']}，¥{el['price']:.2f}，{el['count']:,}份）\n"
        )
        if contain:
            for ca in contain:
                line = f"  - 【{ca['archive_name']}】配比{ca['percentage']}% / {ca['sales_num']:,}份"
                if ca.get("owner"):
                    line += f" / 发行方：{ca['owner']}"
                if ca.get("author"):
                    line += f" / 创作者：{ca['author']}"
                live_min = ca.get("live_min_price") or ca.get("min_price")
                live_total = ca.get("live_total")
                data_source = "实时" if ca.get("live_min_price") else "快照"
                if live_min or live_total is not None:
                    premium = ""
                    if live_min and el.get("price"):
                        ratio = live_min / el["price"]
                        if ratio > 1.05:
                            premium = f"（溢价{(ratio - 1) * 100:.0f}%）"
                        elif ratio < 0.95:
                            premium = f"（破发{(1 - ratio) * 100:.0f}%）"
                    market_info = ""
                    if live_total is not None:
                        market_info += f"在售总量 {live_total:,}件"
                    if live_min:
                        market_info += f"  地板价 ¥{live_min:.2f}{premium}"
                    deal_cnt = ca.get("deal_count") or 0
                    if deal_cnt:
                        market_info += f"  成交{deal_cnt}笔"
                    line += f"\n    {data_source}市场：{market_info}"
                elif ca.get("min_price"):
                    line += (
                        f"\n    市场数据（历史快照）：最低价 ¥{ca['min_price']:.1f}，"
                        f"成交{ca.get('deal_count',0)}笔，在售{ca.get('selling_count',0)}件"
                    )
                if ca.get("sku_desc"):
                    line += f"\n    藏品简介：{ca['sku_desc'][:150]}"
                contain_sections += line + "\n"
        if assoc:
            contain_sections += "  关联藏品：" + "、".join(a["archive_name"] for a in assoc[:3]) + "\n"

    # IP 深度画像
    ip_analysis_block = ""
    for ipn, ip_data in (data.get("ip_deep_analysis") or {}).items():
        ip_analysis_block += f"\n**IP：{ipn}**\n"
        ip_analysis_block += f"  - 历史总发行次数：{ip_data.get('total_launches', 0)}次\n"
        ip_analysis_block += f"  - 近30天发行次数（不含今日）：{ip_data.get('recent_30d_launches', 0)}次\n"
        if ip_data.get("fans_count"):
            ip_analysis_block += f"  - IP粉丝数：{ip_data['fans_count']:,}\n"
        if ip_data.get("description"):
            ip_analysis_block += f"  - IP简介：{ip_data['description'][:200]}\n"
        # 上次发行（DAILY.md 要求）
        last = ip_data.get("last_launch")
        if last:
            ip_analysis_block += (
                f"  - 上次发行：{last['sell_time']}，《{last['name']}》，"
                f"¥{last['price']:.2f}，{last['count']:,}份\n"
            )
        else:
            ip_analysis_block += "  - 上次发行：暂无记录\n"
        # IP 昨日市场快照（来自 MarketIPSnapshot，DAILY.md 要求）
        snap_data = ip_data.get("market_snapshot") or {}
        yd_snap = snap_data.get("yesterday")
        if yd_snap:
            rate = yd_snap.get("deal_count_rate")
            rate_str = f"（{'+' if rate and rate >= 0 else ''}{rate:.1f}%）" if rate is not None else ""
            mv = yd_snap.get("market_amount")
            ip_analysis_block += (
                f"  - 昨日市场：成交 **{yd_snap.get('deal_count', 'N/A')}笔**{rate_str}"
            )
            if mv:
                ip_analysis_block += f"，市值 ¥{mv:,.0f}"
            ip_analysis_block += "\n"
        else:
            ip_analysis_block += "  - 昨日市场快照：暂无数据\n"
        for owner_info in (ip_data.get("owners") or []):
            ip_analysis_block += (
                f"  - 发行主体「{owner_info['name']}」：历史共发行 {owner_info['total_sku_count']} 件藏品"
            )
            if owner_info.get("recent_works"):
                ip_analysis_block += f"，近期代表作：{'、'.join(owner_info['recent_works'][:4])}"
            # 旗下合作IP（DAILY.md 要求的"发行商旗下 IP 矩阵"）
            other_ips = owner_info.get("other_ips") or []
            if other_ips:
                ip_analysis_block += f"，旗下合作IP：{'、'.join(other_ips[:6])}"
            ip_analysis_block += "\n"

    # 行情分析块（_build_market_block 中使用 avg_price_rate 字段）
    market_block = _build_market_block(data.get("market_analysis") or {})

    # 第一阶段核实结果（由 llm.py 注入到 data["_verified_facts"]）
    # 放置于 prompt 顶部，要求 LLM 优先使用这里的数字而非自行推算
    verified_facts = (data.get("_verified_facts") or "").strip()
    verified_section = ""
    if verified_facts:
        verified_section = f"""## ✅ 第一阶段已核实数据事实（以下 JSON 中的数字为权威数据源）
> **写作规则**：所有数值必须来自此处，不得使用原始数据表中的其他计算结果，不得推算。

```json
{verified_facts}
```

---
"""

    return f"""{verified_section}请为以下数据撰写一篇**数藏日报**微信公众号文章。

---
## 基础数据
- 日期：{data['date']}
- 今日发行：**{data['total_launches']} 项**，总量 **{data['total_supply']:,} 份**，总价值 **¥{data['total_value']:,.0f}**
- 均价 ¥{data['avg_price']:.2f}（最高 ¥{data['max_price']:.2f} / 最低 ¥{data['min_price']:.2f}）
- **预计算市场成交量日环比：{market_change_disp}**（Python 预计算）

## 发行清单
| # | 名称 | IP | 单价 | 数量 | 总价值 | 优先购 |
|---|------|----|------|------|--------|--------|
{launches_table}
## 含品与市场数据
{contain_sections or '（暂无含品数据）'}

## IP 深度画像
{ip_analysis_block or '（暂无IP画像数据）'}

## 二级市场行情（昨日快照）
{market_block}

## 可用图表：{', '.join(available_charts)}

---
## 撰写要求

请按以下四段结构撰写 **1500-2200 字** 微信公众号文章，**语言风格参照券商研报，克制客观，禁止营销号风格**：

```
# 数藏日报·{data['date']}｜[1句话概括今日核心数据，纯陈述句，无感叹号/问号]

今日共有 X 项数字藏品发行，总供应量 X 份，总价值 ¥X。[直接点明核心数据，无需铺垫]

## 今日发售日历
[先用 1-2 句概述今日整体发行规模：发行项数、总量、总价值；
 逐项列出所有发行品：名称、IP、价格、数量、是否含优先购；
 含品单独标注在售总量（live_total）和地板价（live_min_price）实时数据]
![今日发行总览](CHART:launch_grid)  ← 若可用

## 重点藏品解读
[对每件含品逐一分析（无含品时分析发行主力IP整体特征）：
  1. 题材与背景（结合 sku_desc 关键信息）：
     - 文物/字画/历史题材 → 客观介绍相关历史文化背景
     - 联名/IP题材 → 简述IP背景、品牌定位
  2. 发行量 & 稀缺性：配比%、发行份数（低配比=小概率获得=高稀缺）
  3. 市场现状（从「已核实数据事实」取 archive_premiums 对应项）：
     - 实时在售总量（live_total）、地板价（live_min_price）
     - 溢价状态：直接使用 premium_pct 和 assessment，不得自行推算
  4. 一句客观陈述（含"仅供参考，不构成投资建议"）]

## IP与发行商分析
[每个今日发行IP独立小节：

### IP名称
- 发行频次：历史总次数 + 近30天次数 → 活跃度等级（取「已核实数据事实」ip_analysis 中的 activity_level）
- 上次发行时间与作品（取 last_launch_time/last_launch_name）
- 昨日市场表现：成交笔数 + 市值变化（取 yesterday_deal_count/yesterday_deal_count_rate，无则注明「暂无快照」）
- 发行商分析：历史总件数 + 近期代表作 + 旗下合作IP矩阵（若该IP无含品数据则跳过发行商分析）]

## 昨日行情复盘
[按以下顺序分析：

### 全市场成交概况
  - 昨日成交量 vs 前日：直接使用「已核实数据事实」market_facts 中的 deal_change_pct，
    并给出 market_trend（升温/降温/持平）的定性判断，用一句话说明
  - 近7天市值与成交量走势：结合 summaries_7d 数据，客观陈述趋势变化
![市值成交趋势](CHART:market_trend_line)  ← 若可用

### 板块行情
  - 各板块成交量排行：按 top_planes 前3-5名简析
  - 板块涨跌分布：结合 plane_census 的上涨/下跌藏品数说明市场情况
![板块涨跌分布](CHART:plane_census)  ← 若可用
![板块成交排行](CHART:plane_deal_rank)  ← 若可用

### 热门藏品 Top10
  - 逐一（或分组）分析「已核实数据事实」hot_archives_top10 中的Top藏品：
    列明名称、分类、成交量，结合均价涨跌幅（avg_amount_rate）和地板价说明表现
![热门藏品涨跌](CHART:top_archives)  ← 若可用

### 热门IP成交排行
  - 昨日成交最高的IP排行
  - 简述头部IP的成交量变化
![IP成交排行](CHART:ip_deal_rank)  ← 若可用]

> 数据截止 {data['date']}，市场价格实时变动，内容仅供参考，不构成投资建议。
```

**写作红线（违反则文章不合格）**：
- 所有数字必须来自「已核实数据事实」JSON 或「预计算」标注值，不得自行推算
- `live_total`（在售总量）和 `live_min_price`（地板价）来自实时API，优先使用
- **全文禁止使用感叹号、反问句、省略号等修辞手法**
- **禁止使用任何推荐性用语**（如"不容错过""值得关注""潜力巨大""建议""看好"等）
- **涨跌幅描述必须与数据幅度匹配**（参见System中的涨跌描述规则第6条）
- 文物/字画类藏品须结合历史文化背景客观介绍
- 无行情数据时注明「暂无行情数据」，不得编造"""


def _fmt_rate(v: float | None, suffix: str = "%") -> str:
    """将涨跌幅格式化为 +1.23% / -1.23%，None 返回 —。"""
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}{suffix}"


def _build_market_block(market: dict) -> str:
    """
    将行情快照数据格式化为 Prompt 中的文字块。

    字段注意事项（避免误读）：
      top_planes[i].avg_price_rate — 均价「日涨跌幅 %」，非实际均价
      top_planes[i].deal_price     — 最新成交价（实际价格）
      top_archives[i].avg_amount   — 均价（实际价格）
      top_archives[i].avg_amount_rate — 均价日涨跌幅 %
    """
    if not market or not market.get("has_data"):
        return "（暂无行情快照数据）"

    yd = market["yesterday"]
    db_ = market["day_before"]

    lines: list[str] = []

    # ── 全市场汇总 ──
    lines.append(f"### 昨日全市场汇总（{yd['stat_date']}）")
    lines.append(
        f"- 总成交笔数：**{yd['total_deal_count']:,}**"
        + (f"（前日 {db_['total_deal_count']:,}）" if db_ else "")
    )
    if yd.get("total_deal_amount"):
        lines.append(
            f"- 总成交额：**¥{yd['total_deal_amount']:,.0f}**"
            + (f"（前日 ¥{db_['total_deal_amount']:,.0f}）" if db_ and db_.get("total_deal_amount") else "")
        )
    if yd.get("total_market_value"):
        lines.append(f"- 全市场总市值：¥{yd['total_market_value']:,.0f}")
    lines.append(f"- 有成交板块数：{yd['active_plane_count']}")
    if yd.get("top_plane_name"):
        lines.append(f"- 成交量最高板块：**{yd['top_plane_name']}**（{yd['top_plane_deal_count']:,} 笔）")
    if yd.get("top_ip_name"):
        lines.append(f"- 成交量最高IP：**{yd['top_ip_name']}**（{yd['top_ip_deal_count']:,} 笔）")

    # ── 近7天全市场趋势（DAILY.md 要求的 summaries_7d，用于折线图数据分析）──
    summaries_7d = market.get("summaries_7d") or []
    if summaries_7d:
        lines.append("\n### 近7天全市场趋势")
        lines.append("| 日期 | 成交量 | 成交额 | 总市值 |")
        lines.append("|------|--------|--------|--------|")
        for s in summaries_7d:
            mv = s.get("total_market_value") or 0
            amt = s.get("total_deal_amount") or 0
            cnt = s.get("total_deal_count") or 0
            lines.append(
                f"| {s['stat_date']} | {cnt:,}笔 "
                f"| ¥{amt/10000:,.1f}万 "
                f"| ¥{mv/1e8:.2f}亿 |"
            )

    # ── 板块排行（avg_price_rate = 均价日涨跌幅%，deal_price = 最新成交价）──
    top_planes = market.get("top_planes") or []
    if top_planes:
        lines.append("\n### 板块成交排行（Top 8）")
        lines.append("| 板块 | 成交量 | 最新成交价 | 均价涨跌幅% | 挂售率 | 总市值 |")
        lines.append("|------|--------|-----------|-----------|--------|--------|")
        for p in top_planes:
            dp = f"¥{p['deal_price']:.2f}" if p.get("deal_price") else "—"
            tmv = f"¥{p['total_market_value']:,.0f}" if p.get("total_market_value") else "—"
            sr = f"{p['shelves_rate']:.1f}%" if p.get("shelves_rate") else "—"
            lines.append(
                f"| {p['plane_name']} | {p['deal_count']:,} "
                f"| {dp} "
                # avg_price_rate = 均价日涨跌幅 %（字段已在 analyzer.py 中重命名以消歧义）
                f"| {_fmt_rate(p.get('avg_price_rate'))} "
                f"| {sr} "
                f"| {tmv} |"
            )

    # ── 板块涨跌分布 ──
    plane_census = market.get("plane_census") or []
    if plane_census:
        lines.append("\n### 板块涨跌分布（Top 10 成交板块）")
        lines.append("| 板块 | 成交量 | 成交量变化 | 市值变化 | 上涨 | 下跌 | 总藏品 |")
        lines.append("|------|--------|-----------|---------|------|------|--------|")
        for c in plane_census:
            lines.append(
                f"| {c['plane_name']} | {c['total_deal_count']:,} "
                f"| {_fmt_rate(c.get('total_deal_count_rate'))} "
                f"| {_fmt_rate(c.get('total_market_amount_rate'))} "
                f"| {c.get('up_archive_count', 0)} "
                f"| {c.get('down_archive_count', 0)} "
                f"| {c.get('total_archive_count', 0)} |"
            )

    # ── 行情分类成交 ──
    top_census = market.get("top_census") or []
    if top_census:
        lines.append("\n### 行情分类成交概况")
        lines.append("| 分类 | 成交量 | 成交量变化 | 市值变化 | 上涨 | 下跌 |")
        lines.append("|------|--------|-----------|---------|------|------|")
        for c in top_census:
            lines.append(
                f"| {c['top_name']} | {c['total_deal_count']:,} "
                f"| {_fmt_rate(c.get('total_deal_count_rate'))} "
                f"| {_fmt_rate(c.get('total_market_amount_rate'))} "
                f"| {c.get('up_archive_count', 0)} "
                f"| {c.get('down_archive_count', 0)} |"
            )

    # ── 全局 Top10 热门藏品（DAILY.md 要求，hot_archives_top10）──
    hot10 = market.get("hot_archives_top10") or []
    if hot10:
        lines.append("\n### 成交量全局 Top 10 藏品")
        lines.append("| 排名 | 藏品 | 分类 | 成交量 | 均价 | 均价涨跌 | 地板价 |")
        lines.append("|------|------|------|--------|------|---------|--------|")
        for i, a in enumerate(hot10, 1):
            avg = f"¥{a['avg_amount']:.2f}" if a.get("avg_amount") else "—"
            mn = f"¥{a['min_amount']:.2f}" if a.get("min_amount") else "—"
            lines.append(
                f"| {i} | {a['archive_name']} | {a['top_name']}"
                f"| {a.get('deal_count', '—')} | {avg}"
                f"| {_fmt_rate(a.get('avg_amount_rate'))} "
                f"| {mn} |"
            )

    # ── 分类 Top 藏品（按分类分组，用于 chart_top_archives 图表）──
    top_archives = market.get("top_archives") or []
    if top_archives:
        # 按分类分组
        cat_map: dict[str, list[dict]] = {}
        for a in top_archives:
            cat_map.setdefault(a["top_name"], []).append(a)
        lines.append("\n### 各分类 Top 藏品")
        for cat, items in cat_map.items():
            lines.append(f"\n**{cat}**")
            lines.append("| 排名 | 藏品 | 成交量 | 均价 | 均价涨跌 | 最低价 |")
            lines.append("|------|------|--------|------|---------|--------|")
            for a in items:
                avg = f"¥{a['avg_amount']:.2f}" if a.get("avg_amount") else "—"
                mn = f"¥{a['min_amount']:.2f}" if a.get("min_amount") else "—"
                lines.append(
                    f"| {a['rank']} | {a['archive_name']} | {a.get('deal_count') or '—'} "
                    f"| {avg} "
                    f"| {_fmt_rate(a.get('avg_amount_rate'))} "
                    f"| {mn} |"
                )

    return "\n".join(lines)
