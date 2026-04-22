"""图表层公共入口 — 统一导出所有图表函数。"""
from .trend import (
    chart_daily_trend,
    chart_value_trend,
    chart_weekly_breakdown,
    chart_three_week_compare,
    chart_market_daily_trend,
)
from .ranking import chart_ip_ranking, chart_ip_market_ranking
from .cover import generate_cover
from .cards import generate_launch_grid
from .market import (
    chart_market_overview,
    chart_plane_census,
    chart_top_archives,
    chart_hot_archives_top10,
    chart_plane_deal_rank,
    chart_market_trend_line,
    chart_ip_deal_rank,
)

__all__ = [
    "chart_daily_trend",
    "chart_value_trend",
    "chart_weekly_breakdown",
    "chart_three_week_compare",
    "chart_market_daily_trend",
    "chart_ip_ranking",
    "chart_ip_market_ranking",
    "generate_cover",
    "generate_launch_grid",
    "chart_market_overview",
    "chart_plane_census",
    "chart_top_archives",
    "chart_hot_archives_top10",
    "chart_plane_deal_rank",
    "chart_market_trend_line",
    "chart_ip_deal_rank",
]
