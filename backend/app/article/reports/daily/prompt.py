"""日报 Prompt 构建 + 系统提示词。"""

SYSTEM_PROMPT = """你是一位专业的数字藏品行业分析师和自媒体作者，擅长撰写微信公众号图文分析文章。

## 写作要求
1. 文章结构清晰，使用 Markdown 格式输出
2. **所有数据必须来自提供的数据，严禁编造任何数字或事实**
3. 分析有深度，结合行业背景、IP历史、发行主体背景给出独到见解
4. 语言专业流畅，适合数藏爱好者和投资者阅读，避免平铺直叙
5. 善用对比、趋势、排行等维度增强分析价值

## 微信公众号格式规范
- 文章标题（第一行 `# 标题`）要吸引眼球，可含数字、关键词、日期
- 一级章节用 `## 一级标题`，二级用 `### 二级标题`
- 开头段落要有钩子，吸引读者继续阅读
- 关键数字和结论用 `**加粗**` 标注
- 每个主要章节后插入对应图表（使用下方标记格式）
- 适当使用项目符号列表（`-`）呈现多维度数据
- 文末加「编辑签名」风格的简短结语，例如：> 💡 数据截止 XX，如有出入以官方为准。

## 可用图表标记
- `![发行藏品总览](CHART:launch_grid)` — 当日发行藏品封面卡片图
- `![发行趋势](CHART:daily_trend)` — 近7天发行数量柱状图
- `![IP排行](CHART:ip_ranking)` / `![IP分布](CHART:ip_distribution)` — IP排行/分布图
- `![价值趋势](CHART:value_trend)` — 发行价值趋势图
- `![月度各周概况](CHART:weekly_breakdown)` — 月度各周分组图

**仅使用 available_charts 中列出的图表键名，未列出则不插入。**"""


def build_daily_prompt(data: dict, available_charts: list[str]) -> str:
    # 发行清单
    launches_table = ""
    for i, l in enumerate(data["launches"][:30], 1):
        prio = f"优先购{l['priority_purchase_num']:,}份" if l["is_priority_purchase"] else "—"
        launches_table += (
            f"| {i} | {l['name']} | {l['ip_name']} "
            f"| ¥{l['price']:.2f} | {l['count']:,} | ¥{l['value']:,.0f} | {prio} |\n"
        )

    # 含品详情
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
                if ca.get("min_price"):
                    premium = ""
                    if ca.get("sales_num") and ca["min_price"] > el["price"] * ca["percentage"] / 100:
                        ratio = (
                            ca["min_price"] / (el["price"] * ca["percentage"] / 100)
                            if el["price"] else 0
                        )
                        if ratio > 1:
                            premium = f"（溢价约{(ratio - 1) * 100:.0f}%）"
                    line += (
                        f"\n    市场最低价 ¥{ca['min_price']:.1f}，"
                        f"成交{ca['deal_count']}笔，在售{ca['selling_count']}件{premium}"
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
        for owner_info in (ip_data.get("owners") or []):
            ip_analysis_block += (
                f"  - 发行主体「{owner_info['name']}」：历史共发行 {owner_info['total_sku_count']} 件藏品"
            )
            if owner_info.get("recent_works"):
                ip_analysis_block += f"，近期代表作：{'、'.join(owner_info['recent_works'][:4])}"
            ip_analysis_block += "\n"

    # 趋势摘要
    trend_str = ""
    for t in data.get("daily_trend") or []:
        trend_str += f"  {t['date']}：{t['count']}项，总值¥{t['value']:,.0f}\n"

    return f"""请为以下数据撰写一篇**数藏日报**微信公众号文章。

---
## 📊 基础数据
- 日期：{data['date']}
- 今日发行：**{data['total_launches']} 项**，总量 **{data['total_supply']:,} 份**，总价值 **¥{data['total_value']:,.0f}**
- 均价 ¥{data['avg_price']:.2f}（最高 ¥{data['max_price']:.2f} / 最低 ¥{data['min_price']:.2f}）
- 昨日发行：{data['yesterday_launches']} 项 / 上周同日：{data['last_week_same_day_launches']} 项

## 📋 发行清单
| # | 名称 | IP | 单价 | 数量 | 总价值 | 优先购 |
|---|------|----|------|------|--------|--------|
{launches_table}
## 🎨 含品与市场数据
{contain_sections or '（暂无含品数据）'}

## 🏷️ IP 深度画像
{ip_analysis_block or '（暂无IP画像数据）'}

## 📈 近7天趋势
{trend_str}

## 可用图表：{', '.join(available_charts)}

---
## 📝 撰写要求

请撰写一篇 **1500-2200 字** 的微信公众号数藏日报，结构如下：

```
# [吸引眼球的标题，含日期+核心亮点，例如：数藏日报 | 4月9日：XXIP双发，XX藏品溢价XX%]

[开篇导语：2-3句话抓住今日最大看点，制造阅读欲望]

![发行藏品总览](CHART:launch_grid)  ← 若可用

## 📰 今日速览
[核心数字对比昨日/上周，1-2段]

## 🎭 IP 格局解析
[每个今日发行IP一个小节，分析：
  - 该IP历史发行频次与规律（是密集还是稀缺，与今日数量对比）
  - 联合发行主体背景（机构规模、历史藏品数量、过往代表作）
  - 历史作品市场表现（溢价/滞销趋势）
  - IP粉丝基础与市场认可度]

## 💎 重点藏品解读
[选取今日2-3件最值得关注的含品，每件从以下角度分析：
  - 藏品本身（题材、工艺、藏品介绍关键词）
  - 配比与稀缺性（低配比=高稀缺）
  - 当前市场价格与溢价幅度
  - 持有建议（可含"仅供参考"免责声明）]

## 📊 二级市场表现
[overview 今日所有含品的价格层次，指出溢价最高与最低（滞销）的藏品]

## 🔮 总结与明日展望
[1段总结今日核心趋势，1句话展望]

> 💡 以上数据来源于鲸探平台，截止发布时间，市场价格实时变动，内容仅供参考。
```

注意：标题中的具体数字（溢价率等）必须来自数据，如无具体数据则换其他亮点角度。"""
