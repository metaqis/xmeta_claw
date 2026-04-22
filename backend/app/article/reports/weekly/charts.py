"""周报图表生成。"""
from app.article.charts import (
    chart_daily_trend,
    chart_value_trend,
    chart_ip_ranking,
    chart_three_week_compare,
    chart_market_daily_trend,
    chart_ip_market_ranking,
    generate_cover,
)


def generate_weekly_charts(data: dict, output_dir: str) -> dict[str, str]:
    charts: dict[str, str] = {}

    # ── 封面 ──────────────────────────────────────────────────────────────────
    p = generate_cover(
        f"数藏周报 · {data['start_date']} ~ {data['end_date']}",
        f"共 {data['total_launches']} 项发行 | 总量 {data['total_supply']:,} | 总价值 ¥{data['total_value']:,.0f}",
        output_dir,
    )
    if p:
        charts["cover"] = p

    # ── 发行日趋势（数量柱状） ────────────────────────────────────────────────
    p = chart_daily_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["daily_trend"] = p

    # ── 发行价值趋势（折线） ──────────────────────────────────────────────────
    p = chart_value_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["value_trend"] = p

    # ── 本周 IP 发行排行 ───────────────────────────────────────────────────────
    p = chart_ip_ranking(data.get("ip_ranking", []), output_dir)
    if p:
        charts["ip_ranking"] = p

    # ── 三周发行数量 vs 价值对比 ───────────────────────────────────────────────
    this_week = {
        "start_date": data.get("start_date", ""),
        "end_date": data.get("end_date", ""),
        "total_launches": data.get("total_launches", 0),
        "total_value": data.get("total_value", 0),
    }
    prev_week  = data.get("prev_week") or {}
    prev2_week = data.get("prev2_week") or {}
    if prev_week.get("total_launches") is not None:
        p = chart_three_week_compare(this_week, prev_week, prev2_week, output_dir)
        if p:
            charts["three_week_compare"] = p

    # ── 本周市场日成交趋势 ────────────────────────────────────────────────────
    mw   = data.get("market_week") or {}
    mpw  = data.get("market_prev_week") or {}
    if mw.get("has_data") and mw.get("daily"):
        prev_total = mpw.get("total_deal_count") if mpw.get("has_data") else None
        p = chart_market_daily_trend(mw["daily"], prev_total, output_dir)
        if p:
            charts["market_daily_trend"] = p

    # ── IP 市场成交排行（本周 vs 上周） ──────────────────────────────────────
    ip_market = data.get("ip_market_weekly") or []
    prev_ip_market = data.get("prev_ip_market_weekly") or []
    if ip_market:
        p = chart_ip_market_ranking(ip_market, prev_ip_market, output_dir)
        if p:
            charts["ip_market_ranking"] = p

    return charts
