"""AI 文章生成模块 — 利用 LLM 撰写微信公众号文章"""

import json
import re
from typing import Any

from loguru import logger

from app.agent.llm import client
from app.core.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = """你是一位专业的数字藏品行业分析师和自媒体作者，擅长撰写微信公众号图文分析文章。

写作要求：
1. 文章结构清晰，使用 Markdown 格式
2. 数据准确，所有数字必须来自提供的数据，不得编造
3. 分析有深度，结合行业背景给出见解
4. 语言专业但易懂，适合数藏爱好者阅读
5. 每个主要章节后插入对应图表，使用 `![图表描述](CHART:chart_key)` 格式
6. 一级标题使用 ##，二级标题使用 ###
7. 关键数据使用**加粗**标注
8. 在文末添加简短总结和展望

可用的图表标记（根据实际提供的图表使用）：
- `![发行趋势](CHART:daily_trend)` — 发行数量趋势柱状图
- `![平台分布](CHART:platform_pie)` — 平台分布饼图
- `![IP排行](CHART:ip_ranking)` 或 `![IP分布](CHART:ip_distribution)` — IP排行/分布图
- `![价值趋势](CHART:value_trend)` — 发行总价值趋势折线图
- `![月度各周概况](CHART:weekly_breakdown)` — 月度各周分组柱状图

请根据数据仅使用 available_charts 中列出的图表键名。"""


def _build_daily_prompt(data: dict, available_charts: list[str]) -> str:
    launches_table = ""
    for i, l in enumerate(data["launches"][:30], 1):
        launches_table += (
            f"| {i} | {l['name']} | {l['platform_name']} | {l['ip_name']} "
            f"| ¥{l['price']:.2f} | {l['count']:,} | ¥{l['value']:,.0f} "
            f"| {'是' if l['is_priority_purchase'] else '否'} |\n"
        )

    ip_hist = ""
    for name, cnt in data.get("ip_recent_30d_history", {}).items():
        ip_hist += f"- {name}: 近30天发行 {cnt} 次\n"

    return f"""请为以下数据撰写一篇**数藏日报**微信公众号文章。

## 基本信息
- 日期：{data['date']}
- 当日发行总数：{data['total_launches']} 项
- 总发行量：{data['total_supply']:,} 份
- 总发行价值：¥{data['total_value']:,.0f}
- 均价：¥{data['avg_price']:.2f} | 最高：¥{data['max_price']:.2f} | 最低：¥{data['min_price']:.2f}
- 昨日发行数：{data['yesterday_launches']} 项
- 上周同日发行数：{data['last_week_same_day_launches']} 项

## 发行列表
| # | 名称 | 平台 | IP | 单价 | 数量 | 总价值 | 优先购 |
|---|------|------|----|------|------|--------|--------|
{launches_table}

## 平台分布
{json.dumps(data['platform_distribution'], ensure_ascii=False, indent=2)}

## IP 分布
{json.dumps(data['ip_distribution'][:10], ensure_ascii=False, indent=2)}

## 发行方近30天历史
{ip_hist or '（无相关数据）'}

## 近7天趋势
{json.dumps(data['daily_trend'], ensure_ascii=False, indent=2)}

## 可用图表: {', '.join(available_charts)}

请撰写一篇 800-1500 字的数藏日报文章，包含：
1. 开篇概要（当日亮点）
2. 发行总览（概括性描述+数据表格）
3. 平台与IP分析（结合图表）
4. 重点藏品解读（选2-3个有特色的展开）
5. 与历史数据对比分析
6. 总结与展望"""


def _build_weekly_prompt(data: dict, available_charts: list[str]) -> str:
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

## 平台分布
{json.dumps(data['platform_distribution'], ensure_ascii=False, indent=2)}

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
3. 平台格局分析
4. 热门IP解读
5. 本周重点藏品
6. 环比对比（与上周）
7. 总结与下周展望"""


def _build_monthly_prompt(data: dict, available_charts: list[str]) -> str:
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

## 平台分布
{json.dumps(data['platform_distribution'], ensure_ascii=False, indent=2)}

## IP 月度排行
| # | IP名称 | 发行次数 |
|---|--------|----------|
{ip_table}

## 每日趋势
{json.dumps(data['daily_trend'], ensure_ascii=False, indent=2)}

## 可用图表: {', '.join(available_charts)}

请撰写一篇 1200-2500 字的数藏月报文章，包含：
1. 月度概要（核心数据亮点）
2. 各周数据对比分析（结合图表）
3. 平台格局变化
4. IP 月度表现
5. 发行总量与价值趋势
6. 环比分析（与上月）
7. 月度总结与下月展望"""


async def generate_article_content(
    article_type: str,
    data: dict[str, Any],
    available_charts: list[str],
) -> dict[str, str]:
    """调用 LLM 生成文章，返回 {title, markdown, summary}"""
    if article_type == "daily":
        user_prompt = _build_daily_prompt(data, available_charts)
    elif article_type == "weekly":
        user_prompt = _build_weekly_prompt(data, available_charts)
    elif article_type == "monthly":
        user_prompt = _build_monthly_prompt(data, available_charts)
    else:
        raise ValueError(f"未知文章类型: {article_type}")

    logger.info(f"开始生成 {article_type} 文章, 数据键: {list(data.keys())}")

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=0.4,
    )

    content = response.choices[0].message.content or ""

    # 提取标题 (第一个 # 或 ## 行)
    title = ""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break

    if not title:
        type_names = {"daily": "数藏日报", "weekly": "数藏周报", "monthly": "数藏月报"}
        date_label = data.get("date") or data.get("start_date") or data.get("month_label", "")
        title = f"{type_names.get(article_type, '数藏分析')} · {date_label}"

    # 生成摘要
    summary_resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": "请用一句话（不超过100字）概括以下文章的核心内容，作为微信公众号文章的摘要。"},
            {"role": "user", "content": content[:3000]},
        ],
        max_tokens=200,
        temperature=0.2,
    )
    summary = (summary_resp.choices[0].message.content or "").strip()[:200]

    return {"title": title, "markdown": content, "summary": summary}


def markdown_to_wechat_html(markdown_text: str, chart_urls: dict[str, str]) -> str:
    """将 Markdown 转换为微信公众号兼容的 HTML（内联样式）"""
    import markdown as md

    # 替换图表占位符为实际 img 标签
    def _replace_chart(m):
        key = m.group(1)
        url = chart_urls.get(key, "")
        if url:
            return f'<img src="{url}" style="width:100%;border-radius:8px;margin:16px 0;" />'
        return ""

    text = re.sub(r"!\[.*?\]\(CHART:(\w+)\)", _replace_chart, markdown_text)

    html = md.markdown(text, extensions=["tables", "nl2br"])

    # 应用微信兼容内联样式
    style_map = {
        "<h1": '<h1 style="font-size:22px;font-weight:bold;color:#1a1a2e;border-bottom:2px solid #1677ff;padding-bottom:8px;margin:24px 0 16px;"',
        "<h2": '<h2 style="font-size:20px;font-weight:bold;color:#1a1a2e;border-left:4px solid #1677ff;padding-left:12px;margin:24px 0 12px;"',
        "<h3": '<h3 style="font-size:17px;font-weight:bold;color:#333;margin:20px 0 10px;"',
        "<p": '<p style="font-size:15px;color:#333;line-height:1.8;margin:10px 0;"',
        "<table": '<table style="width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;"',
        "<th": '<th style="background:#f0f5ff;color:#1a1a2e;padding:8px 10px;border:1px solid #e8e8e8;text-align:left;font-weight:600;"',
        "<td": '<td style="padding:8px 10px;border:1px solid #e8e8e8;color:#333;"',
        "<tr": '<tr style="background:#fff;"',
        "<strong": '<strong style="color:#1677ff;"',
        "<blockquote": '<blockquote style="border-left:4px solid #1677ff;padding:12px 16px;margin:16px 0;background:#f0f5ff;color:#555;font-size:14px;"',
        "<ul": '<ul style="padding-left:20px;margin:10px 0;"',
        "<ol": '<ol style="padding-left:20px;margin:10px 0;"',
        "<li": '<li style="font-size:15px;color:#333;line-height:1.8;margin:4px 0;"',
        "<hr": '<hr style="border:none;border-top:1px solid #e8e8e8;margin:24px 0;"',
    }

    for tag, styled in style_map.items():
        html = html.replace(tag, styled)

    # 斑马纹表格行
    html = re.sub(
        r"(<tr style=\"background:#fff;\">)",
        lambda m: m.group(0),
        html,
    )

    # 包裹完整 HTML
    wrapper = (
        '<section style="max-width:600px;margin:0 auto;padding:20px;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,\'Helvetica Neue\',Arial,sans-serif;'
        'color:#333;line-height:1.8;">'
        f"{html}"
        '<section style="text-align:center;padding:20px 0;margin-top:24px;'
        'border-top:1px solid #e8e8e8;color:#999;font-size:12px;">'
        "数据来源：鲸探数据平台 | 自动生成"
        "</section>"
        "</section>"
    )
    return wrapper
