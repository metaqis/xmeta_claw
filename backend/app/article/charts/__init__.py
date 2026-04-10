"""图表层公共入口 — 统一导出所有图表函数。"""
from .trend import chart_daily_trend, chart_value_trend, chart_weekly_breakdown
from .ranking import chart_ip_ranking
from .cover import generate_cover
from .cards import generate_launch_grid
from .market import (
    chart_market_overview,
    chart_plane_census,
    chart_top_archives,
    chart_plane_deal_rank,
)

__all__ = [
    "chart_daily_trend",
    "chart_value_trend",
    "chart_weekly_breakdown",
    "chart_ip_ranking",
    "generate_cover",
    "generate_launch_grid",
    "chart_market_overview",
    "chart_plane_census",
    "chart_top_archives",
    "chart_plane_deal_rank",
]
