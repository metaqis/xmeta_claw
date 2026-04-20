"""月报 Prompt 构建。"""
import json


def build_monthly_prompt(data: dict, available_charts: list[str]) -> str:
    weekly_table = ""
    for w in data.get("weekly_breakdown", []):
        weekly_table += (
            f"| 第{w['week']}周 ({w['start']}-{w['end']}) "
            f"| {w['launches']} | {w['supply']:,} | ¥{w['value']:,.0f} |\n"
        )

    ip_table = ""
    for i, ip in enumerate(data.get("ip_ranking", [])[:10], 1):
        ip_table += f"| {i} | {ip['name']} | {ip['count']} |\n"

    return f"""请为以下数据撰写一篇**数藏月报**微信公众号文章。

## 基本信息
- 月份：{data['month_label']}
- 本月发行总数：{data['total_launches']} 项
- 总发行量：{data['total_supply']:,} 份
- 总发行价值：¥{data['total_value']:,.0f}
- 均价：¥{data['avg_price']:.2f}
- 上月发行数：{data['prev_month_launches']} 项（变化 {data['launches_change']:+d}）
- 上月总价值：¥{data['prev_month_value']:,.0f}（变化 ¥{data['value_change']:+,.0f}）
- 本月新增藏品数：{data['new_archive_count']}

## 各周概况
| 周 | 发行数 | 发行量 | 总价值 |
|----|--------|--------|--------|
{weekly_table}

## IP 月度排行
| # | IP名称 | 发行次数 |
|---|--------|----------|
{ip_table}

## 每日趋势
{json.dumps(data['daily_trend'], ensure_ascii=False, indent=2)}

## 可用图表: {', '.join(available_charts)}

**重要：文章标题（第一行 `# 标题`）不得超过32个字（含标点符号和空格），格式为「数藏月报·月份｜摘要」。**

请撰写一篇 1200-2500 字的数藏月报文章，包含：
1. 月度概要（核心数据亮点）
2. 各周数据对比分析（结合图表）
3. IP 月度表现
4. 发行总量与价值趋势
5. 环比分析（与上月）
6. 月度总结与下月展望"""
