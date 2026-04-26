"""周报图表生成。"""
from app.article.charts import (
    chart_daily_trend,
    chart_value_trend,
    chart_ip_ranking,
    chart_three_week_compare,
    chart_market_daily_trend,
    chart_ip_market_ranking,
    generate_cover,
    generate_launch_grid,
    chart_plane_deal_rank,
    chart_hot_archives_top10,
    chart_core_plane_market_line,
    chart_ip_deal_rank,
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

    # ── 本周发行日历卡片图 ────────────────────────────────────────────────────
    p = generate_launch_grid(data.get("launches", []), output_dir, "weekly_launch_grid.png")
    if p:
        charts["launch_grid"] = p

    # ── 三周发行规模对比 ──────────────────────────────────────────────────────
    this_week  = {"start_date": data.get("start_date", ""), "end_date": data.get("end_date", ""),
                  "total_launches": data.get("total_launches", 0), "total_value": data.get("total_value", 0)}
    prev_week  = data.get("prev_week") or {}
    prev2_week = data.get("prev2_week") or {}
    if prev_week.get("total_launches") is not None:
        p = chart_three_week_compare(this_week, prev_week, prev2_week, output_dir)
        if p:
            charts["three_week_compare"] = p

    # ── IP 发行排行 ───────────────────────────────────────────────────────────
    p = chart_ip_ranking(data.get("ip_ranking", []), output_dir)
    if p:
        charts["ip_ranking"] = p

    # ── 本周市场每日成交趋势 ──────────────────────────────────────────────────
    mw  = data.get("market_week") or {}
    mpw = data.get("market_prev_week") or {}
    if mw.get("has_data") and mw.get("daily"):
        prev_total = mpw.get("total_deal_count") if mpw.get("has_data") else None
        p = chart_market_daily_trend(mw["daily"], prev_total, output_dir)
        if p:
            charts["market_daily_trend"] = p

    # ── 核心板块（鲸探50/禁出195）本周每日市值折线 ───────────────────────────
    p = chart_core_plane_market_line(
        data.get("week_core_plane_values", []), output_dir, "weekly_core_plane_line.png"
    )
    if p:
        charts["core_plane_market_line"] = p

    # ── 本周板块累计成交排行 ──────────────────────────────────────────────────
    if data.get("week_top_planes"):
        p = chart_plane_deal_rank(
            data["week_top_planes"], output_dir, "weekly_plane_deal_rank.png"
        )
        if p:
            charts["plane_deal_rank"] = p

    # ── 本周热门藏品 Top10 ────────────────────────────────────────────────────
    if data.get("week_hot_archives"):
        p = chart_hot_archives_top10(
            data["week_hot_archives"], output_dir, "weekly_hot_archives.png"
        )
        if p:
            charts["hot_archives_top10"] = p

    # ── IP 市场成交排行（本周 vs 上周对比柱状） ───────────────────────────────
    ip_market      = data.get("ip_market_weekly") or []
    prev_ip_market = data.get("prev_ip_market_weekly") or []
    if ip_market:
        p = chart_ip_market_ranking(ip_market, prev_ip_market, output_dir)
        if p:
            charts["ip_market_ranking"] = p

    # ── IP 成交蝴蝶图（Top5 成交量/市值，用周累计数据） ─────────────────────
    hot_ips = [
        {
            "ip_name": x["name"],
            "deal_count": x["week_deal_count"],
            "market_amount": x.get("avg_market_amount") or 0,
            "deal_count_rate": None,
        }
        for x in ip_market[:5]
    ]
    if hot_ips:
        p = chart_ip_deal_rank(hot_ips, output_dir, "weekly_ip_deal_rank.png")
        if p:
            charts["ip_deal_rank"] = p

    return charts
