"""趋势图表 — 日发行数量柱状图、价值折线图、月度周分组图、三周对比、市场日成交趋势。"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .base import COLORS, TEXT_COLOR, GRID_COLOR, BG_COLOR, setup_ax, save_fig, ensure_dir


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


def chart_three_week_compare(
    this_week: dict,
    prev_week: dict,
    prev2_week: dict,
    output_dir: str,
    filename: str = "three_week_compare.png",
) -> str:
    """
    三周发行数据对比分组柱状图：发行项数（左轴）+ 总价值万元（右轴）。

    参数各 dict 须含 total_launches / total_value / start_date / end_date。
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)

    def _label(w: dict) -> str:
        sd = (w.get("start_date") or "")[-5:]
        ed = (w.get("end_date") or "")[-5:]
        return f"{sd}~{ed}"

    weeks = [prev2_week, prev_week, this_week]
    labels = [_label(w) for w in weeks]
    launches = [w.get("total_launches", 0) for w in weeks]
    values   = [w.get("total_value", 0) / 10000 for w in weeks]

    x = np.arange(len(labels))
    bar_w = 0.35

    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor(BG_COLOR)
    setup_ax(ax1, "三周发行数量 vs 总价值对比")

    bars1 = ax1.bar(x - bar_w / 2, launches, bar_w, label="发行项数", color=COLORS[0], zorder=3)
    for bar, v in zip(bars1, launches):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(launches) * 0.02,
                 str(v), ha="center", va="bottom", fontsize=9, color=TEXT_COLOR)
    ax1.set_ylabel("发行项数", fontsize=10, color=COLORS[0])
    ax1.tick_params(axis="y", labelcolor=COLORS[0])

    ax2 = ax1.twinx()
    ax2.set_facecolor(BG_COLOR)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_color(GRID_COLOR)
    bars2 = ax2.bar(x + bar_w / 2, values, bar_w, label="总价值(万)", color=COLORS[1], zorder=3)
    for bar, v in zip(bars2, values):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.02,
                 f"{v:.0f}", ha="center", va="bottom", fontsize=9, color=COLORS[1])
    ax2.set_ylabel("总价值（万元）", fontsize=10, color=COLORS[1])
    ax2.tick_params(axis="y", labelcolor=COLORS[1])

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=9)
    lines1, lbs1 = ax1.get_legend_handles_labels()
    lines2, lbs2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, lbs1 + lbs2, loc="upper left", fontsize=9)
    save_fig(fig, path)
    return path


def chart_market_daily_trend(
    daily: list[dict],
    prev_total: int | None,
    output_dir: str,
    filename: str = "market_daily_trend.png",
) -> str:
    """
    本周市场日成交趋势折线图（含每日数据标注）。

    daily 每项含 date / deal_count / deal_amount。
    prev_total 为上周同期累计成交量，在图上绘制参考虚线。
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not daily:
        return ""

    dates  = [d["date"][-5:] for d in daily]
    counts = [d.get("deal_count") or 0 for d in daily]

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor(BG_COLOR)
    setup_ax(ax, "本周市场日成交趋势（笔数）")

    ax.bar(dates, counts, color=COLORS[0], width=0.5, zorder=3, alpha=0.75, label="本周日成交")
    ax.plot(dates, counts, marker="o", color=COLORS[0], linewidth=2, markersize=5, zorder=4)
    for i, v in enumerate(counts):
        if v:
            ax.text(i, v + max(counts) * 0.03, f"{v:,}", ha="center", fontsize=8, color=TEXT_COLOR)

    # 上周日均参考线
    if prev_total and len(daily) > 0:
        avg_prev = prev_total / 7
        ax.axhline(avg_prev, color=COLORS[3], linewidth=1.2, linestyle="--",
                   label=f"上周日均 {avg_prev:,.0f}")

    ax.set_ylabel("成交笔数", fontsize=10, color=TEXT_COLOR)
    ax.legend(fontsize=9, loc="upper right")
    save_fig(fig, path)
    return path
