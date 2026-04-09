"""日报图表生成。"""
from app.article.charts import (
    chart_daily_trend,
    chart_ip_ranking,
    chart_value_trend,
    generate_launch_grid,
    generate_cover,
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

    return charts
