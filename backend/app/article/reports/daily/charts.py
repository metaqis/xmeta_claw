"""日报图表生成。"""
from app.article.charts import (
    chart_ip_ranking,
    generate_launch_grid,
    generate_cover,
    chart_market_overview,
    chart_plane_census,
    chart_top_archives,
    chart_plane_deal_rank,
    chart_market_trend_line,
    chart_ip_deal_rank,
)


def generate_daily_charts(data: dict, output_dir: str) -> dict[str, str]:
    charts: dict[str, str] = {}


    ips = data.get("ip_distribution", [])
    if ips:
        p = chart_ip_ranking(ips, output_dir, "ip_distribution.png")
        if p:
            charts["ip_distribution"] = p

    # ── 发行藏品卡片总览 ────────────────────────────────────────────────────
    launches_for_grid = data.get("enriched_launches") or data.get("launches", [])
    p = generate_launch_grid(launches_for_grid, output_dir)
    if p:
        charts["launch_grid"] = p

    # ── 微信封面图 ──────────────────────────────────────────────────────────
    p = generate_cover(
        f"数藏日报 · {data['date']}",
        f"共 {data['total_launches']} 项发行 | 总量 {data['total_supply']:,} | 总价值 ¥{data['total_value']:,.0f}",
        output_dir,
    )
    if p:
        charts["cover"] = p

    # ── 行情图表 ─────────────────────────────────────────────────────────────
    market = data.get("market_analysis") or {}
    if market.get("has_data"):

        # 近7天市值 & 成交量折线图（DAILY.md 要求的 line 图表）
        p = chart_market_trend_line(market.get("summaries_7d", []), output_dir)
        if p:
            charts["market_trend_line"] = p

        # 昨日 vs 前日概览柱状图
        p = chart_market_overview(
            market.get("yesterday"),
            market.get("day_before"),
            output_dir,
        )
        if p:
            charts["market_overview"] = p

        # 板块成交量排行
        p = chart_plane_deal_rank(market.get("top_planes", []), output_dir)
        if p:
            charts["plane_deal_rank"] = p

        # 板块涨跌分布
        p = chart_plane_census(market.get("plane_census", []), output_dir)
        if p:
            charts["plane_census"] = p

        # 分类 Top5 藏品均价涨跌
        p = chart_top_archives(market.get("top_archives", []), output_dir)
        if p:
            charts["top_archives"] = p

    # ── IP 成交量排行（来自 ip_deep_analysis 中的 market_snapshot 数据） ──────
    ip_snap_list: list[dict] = []
    for ip_name, ip_data in (data.get("ip_deep_analysis") or {}).items():
        snap = (ip_data.get("market_snapshot") or {}).get("yesterday")
        if snap:
            ip_snap_list.append({
                "ip_name": ip_name,
                "deal_count": snap.get("deal_count") or 0,
                "deal_count_rate": snap.get("deal_count_rate"),
                "market_amount": snap.get("market_amount"),
            })
    if ip_snap_list:
        p = chart_ip_deal_rank(ip_snap_list, output_dir)
        if p:
            charts["ip_deal_rank"] = p

    return charts

