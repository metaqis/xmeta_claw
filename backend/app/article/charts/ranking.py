"""排行图表 — IP 横向条形排行图、IP 市场成交对比图。"""
import os

import matplotlib.pyplot as plt
import numpy as np

from .base import COLORS, TEXT_COLOR, GRID_COLOR, BG_COLOR, setup_ax, save_fig, ensure_dir


def chart_ip_ranking(
    ranking: list[dict],
    output_dir: str,
    filename: str = "ip_ranking.png",
) -> str:
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not ranking:
        return ""
    # ranking 已按降序排列；reversed 后 No.1 在顶部
    items = list(reversed(ranking))
    names = [r["name"][:14] for r in items]
    counts = [r["count"] for r in items]
    n = len(items)

    # 蓝色渐变：Top1 最深，靠后渐浅（注意 items 已 reversed → 索引最大者为 Top1）
    def _shade(idx_from_top: int) -> str:
        # idx_from_top: 0=Top1, 越大越靠后
        if idx_from_top == 0:
            return "#0958d9"  # 深蓝
        if idx_from_top == 1:
            return "#1677ff"
        if idx_from_top == 2:
            return "#4096ff"
        return "#69b1ff"

    colors = [_shade(n - 1 - i) for i in range(n)]

    fig, ax = plt.subplots(figsize=(8, max(3.2, n * 0.5 + 1.2)))
    setup_ax(ax, "IP 发行排行")
    bars = ax.barh(names, counts, color=colors, height=0.62, zorder=3)

    mx = max(counts) if counts else 1
    ax.set_xlim(0, mx * 1.18)
    for bar, c in zip(bars, counts):
        ax.text(
            bar.get_width() + mx * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{c}",
            ha="left", va="center", fontsize=9.5, color=TEXT_COLOR,
            fontweight="bold",
        )
    ax.set_xlabel("发行次数", fontsize=10, color=TEXT_COLOR)
    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_ip_market_ranking(
    this_week: list[dict],
    prev_week: list[dict],
    output_dir: str,
    filename: str = "ip_market_ranking.png",
) -> str:
    """
    本周 vs 上周 IP 市场成交量对比横向分组条形图。

    this_week / prev_week 每项含 name / week_deal_count。
    取两周均出现的 IP 的并集，按本周成交量降序排列，最多展示 Top 10。
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not this_week:
        return ""

    prev_map = {x["name"]: x["week_deal_count"] for x in prev_week}

    # 按本周成交量降序，最多 10 条
    top = this_week[:10]
    names   = [r["name"][:12] for r in reversed(top)]
    cur_cnt = [r["week_deal_count"] for r in reversed(top)]
    prv_cnt = [prev_map.get(r["name"], 0) for r in reversed(top)]

    y = np.arange(len(names))
    bar_h = 0.35

    fig, ax = plt.subplots(figsize=(9, max(4, len(names) * 0.6)))
    fig.patch.set_facecolor(BG_COLOR)
    setup_ax(ax, "本周 vs 上周 IP 市场成交量")

    bars1 = ax.barh(y + bar_h / 2, cur_cnt, bar_h, label="本周", color=COLORS[0], zorder=3)
    bars2 = ax.barh(y - bar_h / 2, prv_cnt, bar_h, label="上周", color=COLORS[2], zorder=3, alpha=0.75)

    max_val = max(max(cur_cnt), max(prv_cnt), 1)
    for bar, v in zip(bars1, cur_cnt):
        if v:
            ax.text(bar.get_width() + max_val * 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{v:,}", ha="left", va="center", fontsize=8, color=TEXT_COLOR)
    for bar, v in zip(bars2, prv_cnt):
        if v:
            ax.text(bar.get_width() + max_val * 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{v:,}", ha="left", va="center", fontsize=8, color=TEXT_COLOR)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("成交笔数", fontsize=10, color=TEXT_COLOR)
    ax.legend(loc="lower right", fontsize=9)
    save_fig(fig, path)
    return path
