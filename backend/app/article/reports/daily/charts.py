"""日报图表生成。"""
from app.article.charts import (
    chart_daily_trend,
    chart_ip_ranking,
    chart_value_trend,
    generate_launch_grid,
    generate_cover,
    chart_market_overview,
    chart_plane_census,
    chart_top_archives,
    chart_plane_deal_rank,
)


def generate_daily_charts(data: dict, output_dir: str) -> dict[str, str]:
    charts: dict[str, str] = {}

    p = chart_daily_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["daily_trend"] = p

    ips = data.get("ip_distribution", [])
    if ips:
        p = chart_ip_ranking(ips, output_dir, "ip_distribution.png")
        if p:
            charts["ip_distribution"] = p

    p = chart_value_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["value_trend"] = p

    launches_for_grid = data.get("enriched_launches") or data.get("launches", [])
    p = generate_launch_grid(launches_for_grid, output_dir)
    if p:
        charts["launch_grid"] = p

    p = generate_cover(
        f"数藏日报 · {data['date']}",
        f"共 {data['total_launches']} 项发行 | 总量 {data['total_supply']:,} | 总价值 ¥{data['total_value']:,.0f}",
        output_dir,
    )
    if p:
        charts["cover"] = p

    # ── 行情图表 ──────────────────────────────────────────────
    market = data.get("market_analysis") or {}
    if market.get("has_data"):
        p = chart_market_overview(
            market.get("yesterday"),
            market.get("day_before"),
            output_dir,
        )
        if p:
            charts["market_overview"] = p

        p = chart_plane_deal_rank(market.get("top_planes", []), output_dir)
        if p:
            charts["plane_deal_rank"] = p

        p = chart_plane_census(market.get("plane_census", []), output_dir)
        if p:
            charts["plane_census"] = p

        p = chart_top_archives(market.get("top_archives", []), output_dir)
        if p:
            charts["top_archives"] = p

    return charts
