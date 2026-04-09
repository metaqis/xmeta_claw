"""周报图表生成。"""
from app.article.charts import (
    chart_daily_trend,
    chart_ip_ranking,
    chart_value_trend,
    generate_cover,
)


def generate_weekly_charts(data: dict, output_dir: str) -> dict[str, str]:
    charts: dict[str, str] = {}

    p = chart_daily_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["daily_trend"] = p

    p = chart_ip_ranking(data.get("ip_ranking", []), output_dir)
    if p:
        charts["ip_ranking"] = p

    p = chart_value_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["value_trend"] = p

    p = generate_cover(
        f"数藏周报 · {data['start_date']} ~ {data['end_date']}",
        f"共 {data['total_launches']} 项发行 | 总量 {data['total_supply']:,} | 总价值 ¥{data['total_value']:,.0f}",
        output_dir,
    )
    if p:
        charts["cover"] = p

    return charts
