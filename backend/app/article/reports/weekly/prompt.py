"""周报 Prompt 构建。"""
import json


def build_weekly_prompt(data: dict, available_charts: list[str]) -> str:
    ip_table = ""
    for i, ip in enumerate(data.get("ip_ranking", [])[:10], 1):
        ip_table += f"| {i} | {ip['name']} | {ip['count']} |\n"

    archives_info = ""
    for a in data.get("new_archives", [])[:10]:
        archives_info += f"- {a['name']}（{a['platform']}，{a['ip']}，数量 {a['goods_count'] or '未知'}）\n"

    return f"""请为以下数据撰写一篇**数藏周报**微信公众号文章。

## 基本信息
- 时间范围：{data['start_date']} ~ {data['end_date']}
- 本周发行总数：{data['total_launches']} 项
- 总发行量：{data['total_supply']:,} 份
- 总发行价值：¥{data['total_value']:,.0f}
- 均价：¥{data['avg_price']:.2f}
- 上周发行数：{data['prev_week_launches']} 项（变化 {data['launches_change']:+d}）
- 上周总价值：¥{data['prev_week_value']:,.0f}（变化 ¥{data['value_change']:+,.0f}）

## 每日趋势
{json.dumps(data['daily_trend'], ensure_ascii=False, indent=2)}

## IP 发行排行
| # | IP名称 | 发行次数 |
|---|--------|----------|
{ip_table}

## 本周新增藏品
{archives_info or '（无新增藏品）'}

## 可用图表: {', '.join(available_charts)}

请撰写一篇 1000-2000 字的数藏周报文章，包含：
1. 本周概要（核心亮点数据）
2. 每日发行趋势分析（结合图表）
3. 热门IP解读
4. 本周重点藏品
5. 环比对比（与上周）
6. 总结与下周展望"""
