"""趋势图表 — 日发行数量柱状图、价值折线图、月度周分组图。"""
import os

import matplotlib.pyplot as plt

from .base import COLORS, TEXT_COLOR, GRID_COLOR, setup_ax, save_fig, ensure_dir


def chart_daily_trend(
    trend: list[dict],
    output_dir: str,
    filename: str = "daily_trend.png",
) -> str:
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not trend:
        return ""
    dates = [d["date"][-5:] for d in trend]
    counts = [d["count"] for d in trend]

    fig, ax = plt.subplots(figsize=(8, 4))
    setup_ax(ax, "日发行数量趋势")
    bars = ax.bar(dates, counts, color=COLORS[0], width=0.6, zorder=3)
    for bar, c in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.2,
            str(c),
            ha="center", va="bottom", fontsize=9, color=TEXT_COLOR,
        )
    ax.set_ylabel("发行数量", fontsize=10, color=TEXT_COLOR)
    save_fig(fig, path)
    return path


def chart_value_trend(
    trend: list[dict],
    output_dir: str,
    filename: str = "value_trend.png",
) -> str:
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not trend:
        return ""
    dates = [d["date"][-5:] for d in trend]
    values = [d["value"] / 10000 for d in trend]

    fig, ax = plt.subplots(figsize=(8, 4))
    setup_ax(ax, "发行总价值趋势（万元）")
    ax.plot(dates, values, marker="o", color=COLORS[0], linewidth=2, markersize=5, zorder=3)
    ax.fill_between(dates, values, alpha=0.1, color=COLORS[0])
    for i, v in enumerate(values):
        if v > 0:
            ax.text(i, v + max(values) * 0.03, f"{v:.1f}", ha="center", fontsize=8, color=TEXT_COLOR)
    ax.set_ylabel("万元", fontsize=10, color=TEXT_COLOR)
    save_fig(fig, path)
    return path


def chart_weekly_breakdown(
    weeks: list[dict],
    output_dir: str,
    filename: str = "weekly_breakdown.png",
) -> str:
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not weeks:
        return ""
    labels = [f"第{w['week']}周\n{w['start']}-{w['end']}" for w in weeks]
    launches = [w["launches"] for w in weeks]
    values = [w["value"] / 10000 for w in weeks]

    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    setup_ax(ax1, "月度各周发行概况")
    x = range(len(labels))
    w = 0.35
    ax1.bar([i - w / 2 for i in x], launches, w, label="发行数", color=COLORS[0], zorder=3)
    ax1.set_ylabel("发行数", fontsize=10, color=COLORS[0])
    ax1.tick_params(axis="y", labelcolor=COLORS[0])

    ax2 = ax1.twinx()
    ax2.bar([i + w / 2 for i in x], values, w, label="总价值(万)", color=COLORS[1], zorder=3)
    ax2.set_ylabel("总价值(万元)", fontsize=10, color=COLORS[1])
    ax2.tick_params(axis="y", labelcolor=COLORS[1])
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_color(GRID_COLOR)

    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels, fontsize=9)
    fig.legend(loc="upper right", bbox_to_anchor=(0.95, 0.95), fontsize=9)
    save_fig(fig, path)
    return path
