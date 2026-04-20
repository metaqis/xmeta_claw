"""市场行情图表 — 板块排行、涨跌分布、热门藏品均价对比。"""
import os

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from .base import COLORS, TEXT_COLOR, GRID_COLOR, BG_COLOR, setup_ax, save_fig, ensure_dir

_UP_COLOR = "#ff4d4f"
_DOWN_COLOR = "#52c41a"
_NEUTRAL = "#1677ff"


def chart_market_overview(
    yesterday: dict | None,
    day_before: dict | None,
    output_dir: str,
    filename: str = "market_overview.png",
) -> str:
    """全市场对比柱状图：昨日 vs 前日的成交笔数 & 成交额。"""
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not yesterday:
        return ""

    labels = ["昨日", "前日"]
    deal_counts = [
        yesterday.get("total_deal_count") or 0,
        (day_before.get("total_deal_count") or 0) if day_before else 0,
    ]
    deal_amounts = [
        yesterday.get("total_deal_amount") or 0,
        (day_before.get("total_deal_amount") or 0) if day_before else 0,
    ]

    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    fig.patch.set_facecolor(BG_COLOR)
    fig.suptitle("全市场概览（昨日 vs 前日）", fontsize=13, fontweight="bold",
                 color=TEXT_COLOR, y=1.01)

    # 成交笔数
    ax1 = axes[0]
    setup_ax(ax1, "总成交笔数")
    bars1 = ax1.bar(labels, deal_counts, color=[_UP_COLOR, COLORS[0]], width=0.5, zorder=3)
    for bar, v in zip(bars1, deal_counts):
        if v:
            ax1.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + max(deal_counts) * 0.02,
                     f"{v:,}", ha="center", va="bottom", fontsize=10, color=TEXT_COLOR)
    ax1.set_ylabel("笔数", fontsize=10, color=TEXT_COLOR)

    # 成交额（万元）
    ax2 = axes[1]
    setup_ax(ax2, "总成交额（万元）")
    amounts_w = [v / 10000 for v in deal_amounts]
    bars2 = ax2.bar(labels, amounts_w, color=[_UP_COLOR, COLORS[0]], width=0.5, zorder=3)
    for bar, v in zip(bars2, amounts_w):
        if v:
            ax2.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + max(amounts_w, default=1) * 0.02,
                     f"{v:,.1f}", ha="center", va="bottom", fontsize=10, color=TEXT_COLOR)
    ax2.set_ylabel("万元", fontsize=10, color=TEXT_COLOR)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_plane_census(
    plane_census: list[dict],
    output_dir: str,
    filename: str = "plane_census.png",
) -> str:
    """板块涨跌分布水平堆叠条形图（上涨绿、下跌红、持平灰）。"""
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not plane_census:
        return ""

    items = plane_census[:10]
    names = [p["plane_name"] for p in items]
    up = [p.get("up_archive_count") or 0 for p in items]
    down = [p.get("down_archive_count") or 0 for p in items]
    total = [p.get("total_archive_count") or 1 for p in items]
    flat = [max(0, t - u - d) for t, u, d in zip(total, up, down)]

    y = np.arange(len(names))
    height = 0.55

    fig, ax = plt.subplots(figsize=(9, max(4, len(names) * 0.55 + 1.5)))
    ax.set_facecolor(BG_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax.set_title("板块藏品涨跌分布", fontsize=13, fontweight="bold", color=TEXT_COLOR, pad=12)

    b_up   = ax.barh(y, up,   height, color=_UP_COLOR,   label="上涨", zorder=3)
    b_flat = ax.barh(y, flat, height, left=up, color="#d9d9d9", label="持平", zorder=3)
    b_dn   = ax.barh(y, down, height, left=[u + f for u, f in zip(up, flat)],
                     color=_DOWN_COLOR, label="下跌", zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9, color=TEXT_COLOR)
    ax.set_xlabel("藏品数量", fontsize=10, color=TEXT_COLOR)
    ax.legend(handles=[b_up, b_flat, b_dn], loc="lower right", fontsize=9)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)

    # 在上涨条右侧标注涨幅比例
    for i, (u, t, p) in enumerate(zip(up, total, items)):
        pct = u / t * 100 if t else 0
        rate = p.get("total_deal_count_rate")
        label = f"{pct:.0f}%涨"
        if rate is not None:
            sign = "+" if rate >= 0 else ""
            label += f"  成交{sign}{rate:.1f}%"
        ax.text(total[i] + max(total) * 0.01, y[i], label,
                va="center", fontsize=8, color=TEXT_COLOR)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_top_archives(
    top_archives: list[dict],
    output_dir: str,
    filename: str = "top_archives.png",
) -> str:
    """各分类 Top 藏品均价涨跌幅对比，按分类分组，横向条形图。"""
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not top_archives:
        return ""

    # 按 top_name 分组，每组最多 5 条
    cat_map: dict[str, list[dict]] = {}
    for a in top_archives:
        cat_map.setdefault(a["top_name"], []).append(a)
    for k in cat_map:
        cat_map[k] = cat_map[k][:5]

    n_cats = len(cat_map)
    if n_cats == 0:
        return ""

    fig, axes = plt.subplots(
        1, n_cats,
        figsize=(min(5 * n_cats, 14), max(4, max(len(v) for v in cat_map.values()) * 0.55 + 1.5)),
        squeeze=False,
    )
    fig.patch.set_facecolor(BG_COLOR)
    fig.suptitle("热门藏品均价涨跌（各分类 Top 5）", fontsize=13, fontweight="bold",
                 color=TEXT_COLOR, y=1.02)

    for col_idx, (cat, items) in enumerate(cat_map.items()):
        ax = axes[0][col_idx]
        ax.set_facecolor(BG_COLOR)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(GRID_COLOR)
        ax.spines["bottom"].set_color(GRID_COLOR)
        ax.tick_params(colors=TEXT_COLOR, labelsize=8)
        ax.set_title(cat, fontsize=11, fontweight="bold", color=TEXT_COLOR, pad=8)

        names = [a["archive_name"][:8] + ("…" if len(a["archive_name"]) > 8 else "")
                 for a in items]
        rates = [a.get("avg_amount_rate") or 0.0 for a in items]
        colors = [_UP_COLOR if r >= 0 else _DOWN_COLOR for r in rates]

        y = np.arange(len(names))
        ax.barh(y, rates, 0.55, color=colors, zorder=3)
        ax.axvline(0, color=TEXT_COLOR, linewidth=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=8, color=TEXT_COLOR)
        ax.set_xlabel("均价涨跌幅 (%)", fontsize=9, color=TEXT_COLOR)
        ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)

        for i, (r, a) in enumerate(zip(rates, items)):
            sign = "+" if r >= 0 else ""
            avg = f"¥{a['avg_amount']:.1f}" if a.get("avg_amount") else ""
            label = f"{sign}{r:.1f}%  {avg}"
            x_off = max(abs(r) * 0.05, abs(max(rates, key=abs, default=1)) * 0.02)
            ax.text(r + (x_off if r >= 0 else -x_off), y[i],
                    label, va="center", ha="left" if r >= 0 else "right",
                    fontsize=7, color=TEXT_COLOR)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_plane_deal_rank(
    top_planes: list[dict],
    output_dir: str,
    filename: str = "plane_deal_rank.png",
) -> str:
    """板块成交量排行横向条形图，含均价涨跌幅颜色标注。"""
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not top_planes:
        return ""

    items = top_planes[:8]
    names = [p["plane_name"] for p in items]
    counts = [p.get("deal_count") or 0 for p in items]
    rates = [p.get("avg_price_rate") or 0.0 for p in items]
    colors = [_UP_COLOR if r >= 0 else _DOWN_COLOR for r in rates]

    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(9, max(4, len(names) * 0.6 + 1.5)))
    setup_ax(ax, "板块成交量排行（附均价涨跌）")
    ax.barh(y, counts, 0.6, color=colors, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9, color=TEXT_COLOR)
    ax.set_xlabel("成交量（笔）", fontsize=10, color=TEXT_COLOR)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)

    mx = max(counts, default=1)
    for i, (c, r) in enumerate(zip(counts, rates)):
        sign = "+" if r >= 0 else ""
        ax.text(c + mx * 0.01, y[i],
                f"{c:,}  均价{sign}{r:.1f}%",
                va="center", fontsize=8, color=TEXT_COLOR)

    # 图例
    up_patch = mpatches.Patch(color=_UP_COLOR, label="均价上涨")
    dn_patch = mpatches.Patch(color=_DOWN_COLOR, label="均价下跌")
    ax.legend(handles=[up_patch, dn_patch], loc="lower right", fontsize=9)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_market_trend_line(
    summaries_7d: list[dict],
    output_dir: str,
    filename: str = "market_trend_line.png",
) -> str:
    """
    近7天全市场市值 & 成交量双轴折线图（DAILY.md：创建 line 图表）。

    左轴：总市值（亿元）
    右轴：成交笔数
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not summaries_7d:
        return ""

    dates = [s["stat_date"][-5:] for s in summaries_7d]  # MM-DD
    market_values = [(s.get("total_market_value") or 0) / 1e8 for s in summaries_7d]  # 亿
    deal_counts = [s.get("total_deal_count") or 0 for s in summaries_7d]

    fig, ax1 = plt.subplots(figsize=(9, 4))
    fig.patch.set_facecolor(BG_COLOR)
    ax1.set_facecolor(BG_COLOR)
    ax1.set_title("近7天市值 & 成交量趋势", fontsize=13, fontweight="bold",
                  color=TEXT_COLOR, pad=10)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_color(COLORS[1])
    ax1.spines["left"].set_color(COLORS[0])
    ax1.spines["bottom"].set_color(GRID_COLOR)
    ax1.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax1.grid(axis="y", color=GRID_COLOR, linewidth=0.5, linestyle="--")

    # 左轴：市值
    line1, = ax1.plot(dates, market_values, marker="o", color=COLORS[0],
                      linewidth=2, markersize=5, label="总市值（亿）", zorder=3)
    ax1.set_ylabel("总市值（亿元）", fontsize=10, color=COLORS[0])
    ax1.tick_params(axis="y", labelcolor=COLORS[0])
    for x, y in zip(dates, market_values):
        if y:
            ax1.annotate(f"{y:.1f}", (x, y), textcoords="offset points",
                         xytext=(0, 7), ha="center", fontsize=8, color=COLORS[0])

    # 右轴：成交量
    ax2 = ax1.twinx()
    ax2.set_facecolor(BG_COLOR)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_color(COLORS[1])
    ax2.tick_params(colors=TEXT_COLOR, labelsize=9, axis="y", labelcolor=COLORS[1])
    line2, = ax2.plot(dates, deal_counts, marker="s", color=COLORS[1],
                      linewidth=2, markersize=5, linestyle="--", label="成交笔数", zorder=3)
    ax2.set_ylabel("成交笔数", fontsize=10, color=COLORS[1])
    for x, y in zip(dates, deal_counts):
        if y:
            ax2.annotate(f"{y:,}", (x, y), textcoords="offset points",
                         xytext=(0, -14), ha="center", fontsize=8, color=COLORS[1])

    # 合并图例
    ax1.legend(handles=[line1, line2], loc="upper left", fontsize=9,
               facecolor=BG_COLOR, labelcolor=TEXT_COLOR)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_ip_deal_rank(
    ip_snapshots: list[dict],
    output_dir: str,
    filename: str = "ip_deal_rank.png",
) -> str:
    """
    昨日 IP 成交量横向条形排行（DAILY.md：热门 IP 分析）。

    ip_snapshots: [{"ip_name": ..., "deal_count": ..., "market_amount": ...,
                    "deal_count_rate": ...}, ...]
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not ip_snapshots:
        return ""

    # 按成交量排序，取 Top 12
    items = sorted(ip_snapshots, key=lambda x: x.get("deal_count") or 0, reverse=True)[:12]
    if not items:
        return ""

    names = [i.get("ip_name") or "—" for i in items]
    counts = [i.get("deal_count") or 0 for i in items]
    rates = [i.get("deal_count_rate") or 0.0 for i in items]
    colors = [_UP_COLOR if r >= 0 else _DOWN_COLOR for r in rates]

    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(9, max(4, len(names) * 0.55 + 1.5)))
    setup_ax(ax, "昨日 IP 成交量排行")
    ax.barh(y, counts, 0.6, color=colors, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9, color=TEXT_COLOR)
    ax.set_xlabel("成交量（笔）", fontsize=10, color=TEXT_COLOR)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)

    mx = max(counts, default=1)
    for i, (c, r) in enumerate(zip(counts, rates)):
        sign = "+" if r >= 0 else ""
        lbl = f"{c:,}"
        if r:
            lbl += f"  ({sign}{r:.1f}%)"
        ax.text(c + mx * 0.01, y[i], lbl, va="center", fontsize=8, color=TEXT_COLOR)

    up_patch = mpatches.Patch(color=_UP_COLOR, label="成交量环比上升")
    dn_patch = mpatches.Patch(color=_DOWN_COLOR, label="成交量环比下降")
    ax.legend(handles=[up_patch, dn_patch], loc="lower right", fontsize=9)

    fig.tight_layout()
    save_fig(fig, path)
    return path

