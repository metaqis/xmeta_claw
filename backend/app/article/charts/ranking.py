"""排行图表 — IP 横向条形排行图。"""
import os

import matplotlib.pyplot as plt

from .base import COLORS, TEXT_COLOR, setup_ax, save_fig, ensure_dir


def chart_ip_ranking(
    ranking: list[dict],
    output_dir: str,
    filename: str = "ip_ranking.png",
) -> str:
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not ranking:
        return ""
    names = [r["name"][:12] for r in reversed(ranking)]
    counts = [r["count"] for r in reversed(ranking)]

    fig, ax = plt.subplots(figsize=(7, max(3, len(names) * 0.5)))
    setup_ax(ax, "IP 发行排行")
    bars = ax.barh(names, counts, color=COLORS[0], height=0.6, zorder=3)
    for bar, c in zip(bars, counts):
        ax.text(
            bar.get_width() + 0.2,
            bar.get_y() + bar.get_height() / 2,
            str(c),
            ha="left", va="center", fontsize=9, color=TEXT_COLOR,
        )
    ax.set_xlabel("发行次数", fontsize=10, color=TEXT_COLOR)
    save_fig(fig, path)
    return path
