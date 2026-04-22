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
    """
    全市场对比：昨日 vs 前日的成交笔数 & 成交额（万元）。

    单图分组柱状：左组=成交笔数、右组=成交额；
    每组中昨日柱按 vs 前日 涨跌染色（红=升温/绿=降温/灰=持平），
    柱顶标注绝对值，组下方标注环比 % 徽章。
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not yesterday:
        return ""

    yc = yesterday.get("total_deal_count") or 0
    yc_amt = (yesterday.get("total_deal_amount") or 0) / 10000  # 万元
    pc = (day_before.get("total_deal_count") or 0) if day_before else 0
    pc_amt = ((day_before.get("total_deal_amount") or 0) / 10000) if day_before else 0

    def _delta_pct(cur, prev):
        if not prev:
            return None
        return (cur - prev) / prev * 100

    d_count = _delta_pct(yc, pc)
    d_amt = _delta_pct(yc_amt, pc_amt)

    def _color(d):
        if d is None:
            return "#8c8c8c"
        if d > 5:
            return _UP_COLOR
        if d < -5:
            return _DOWN_COLOR
        return "#8c8c8c"

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5),
                             gridspec_kw={"wspace": 0.35})
    fig.patch.set_facecolor(BG_COLOR)
    fig.suptitle("全市场概览（昨日 vs 前日）", fontsize=14, fontweight="bold",
                 color=TEXT_COLOR, y=1.02)

    def _draw(ax, title, prev_v, cur_v, delta, unit):
        setup_ax(ax, title)
        labels = ["前日", "昨日"]
        vals = [prev_v, cur_v]
        # 前日始终中性色，昨日按 delta 染色
        colors = ["#bfbfbf", _color(delta)]
        bars = ax.bar(labels, vals, color=colors, width=0.5, zorder=3)
        mx = max(vals + [1])
        ax.set_ylim(0, mx * 1.30)
        for bar, v in zip(bars, vals):
            if v:
                fmt = f"{v:,.1f}" if unit == "万元" else f"{v:,}"
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + mx * 0.025,
                        fmt, ha="center", va="bottom", fontsize=10,
                        color=TEXT_COLOR, fontweight="bold")
        ax.set_ylabel(unit, fontsize=10, color=TEXT_COLOR)

        # 环比徽章
        if delta is not None:
            arrow = "▲" if delta >= 0 else "▼"
            sign = "+" if delta >= 0 else ""
            badge_color = _color(delta)
            badge_text = f"环比 {arrow}{sign}{delta:.1f}%"
            ax.text(0.5, -0.18, badge_text, transform=ax.transAxes,
                    ha="center", va="center", fontsize=11, color="white",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=badge_color,
                              edgecolor="none"))
        else:
            ax.text(0.5, -0.18, "无环比数据", transform=ax.transAxes,
                    ha="center", va="center", fontsize=10, color="#8c8c8c")

    _draw(axes[0], "总成交笔数", pc, yc, d_count, "笔数")
    _draw(axes[1], "总成交额", pc_amt, yc_amt, d_amt, "万元")

    fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.18, wspace=0.35)
    save_fig(fig, path)
    return path


def chart_plane_census(
    plane_census: list[dict],
    output_dir: str,
    filename: str = "plane_census.png",
) -> str:
    """板块涨跌分布水平堆叠条形图（上涨红、持平灰、下跌绿）+ 涨幅占比标签。"""
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

    n = len(names)
    y = np.arange(n)[::-1]
    height = 0.58

    fig, ax = plt.subplots(figsize=(10, max(4.2, n * 0.58 + 1.5)))
    ax.set_facecolor(BG_COLOR)
    fig.patch.set_facecolor(BG_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax.set_title("板块藏品涨跌分布", fontsize=13, fontweight="bold",
                 color=TEXT_COLOR, pad=12)

    b_up = ax.barh(y, up, height, color=_UP_COLOR, label="上涨", zorder=3)
    b_flat = ax.barh(y, flat, height, left=up, color="#d9d9d9",
                     label="持平", zorder=3)
    b_dn = ax.barh(y, down, height,
                   left=[u + f for u, f in zip(up, flat)],
                   color=_DOWN_COLOR, label="下跌", zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=10, color=TEXT_COLOR, fontweight="bold")
    ax.set_xlabel("藏品数量", fontsize=10, color=TEXT_COLOR)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)

    mx_total = max(total) or 1
    # 右侧留 30% 给标签
    ax.set_xlim(0, mx_total * 1.32)

    for i, (u, t, p) in enumerate(zip(up, total, items)):
        up_pct = u / t * 100 if t else 0
        dn_pct = (down[i] / t * 100) if t else 0
        rate = p.get("total_deal_count_rate")

        # 段内白字百分比（只在段宽 ≥ 12% 总宽时显示，避免拥挤）
        if u and u / mx_total > 0.12:
            ax.text(u / 2, y[i], f"{up_pct:.0f}%",
                    va="center", ha="center", fontsize=8.5,
                    color="white", fontweight="bold", zorder=5)
        if down[i] and down[i] / mx_total > 0.12:
            ax.text(u + flat[i] + down[i] / 2, y[i], f"{dn_pct:.0f}%",
                    va="center", ha="center", fontsize=8.5,
                    color="white", fontweight="bold", zorder=5)

        # 右侧汇总标签：上涨/下跌占比 + 成交环比
        parts = [f"↑{up_pct:.0f}% ↓{dn_pct:.0f}%"]
        if rate is not None:
            sign = "+" if rate >= 0 else ""
            arrow = "▲" if rate >= 0 else "▼"
            parts.append(f"成交{arrow}{sign}{rate:.1f}%")
        label = "   ".join(parts)
        ax.text(t + mx_total * 0.015, y[i], label,
                va="center", ha="left", fontsize=9, color=TEXT_COLOR)

    ax.legend(handles=[b_up, b_flat, b_dn], loc="lower right",
              fontsize=9, frameon=False)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_hot_archives_top10(
    hot_archives: list[dict],
    output_dir: str,
    filename: str = "hot_archives_top10.png",
) -> str:
    """
    昨日全局成交量 Top 10 藏品综合卡片图。

    单个横向条形 = 成交量；按均价涨跌幅染色（红涨/绿跌/灰=持平或缺失）。
    左侧：排名徽章；条形上覆盖 [分类] 标签 + 藏品名；右侧三段式：环比% + 均价 + 地板价。

    hot_archives: [{archive_name, top_name, deal_count, avg_amount,
                    avg_amount_rate, min_amount, market_amount}, ...]
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not hot_archives:
        return ""

    items = hot_archives[:10]
    n = len(items)
    if n == 0:
        return ""

    counts = [a.get("deal_count") or 0 for a in items]
    rates = [a.get("avg_amount_rate") for a in items]
    avgs = [a.get("avg_amount") for a in items]
    mins = [a.get("min_amount") for a in items]
    names = [a.get("archive_name") or "—" for a in items]
    cats = [a.get("top_name") or "" for a in items]

    def _color(r):
        if r is None:
            return "#8c8c8c"
        if r > 0.5:
            return _UP_COLOR
        if r < -0.5:
            return _DOWN_COLOR
        return "#8c8c8c"

    colors = [_color(r) for r in rates]

    y = np.arange(n)[::-1]  # No.1 在顶
    fig, ax = plt.subplots(figsize=(11, max(5.5, n * 0.62 + 1.5)))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.set_title("昨日热门藏品 Top 10（成交量 × 均价涨跌）",
                 fontsize=13, fontweight="bold", color=TEXT_COLOR, pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9, left=False)

    bars = ax.barh(y, counts, 0.62, color=colors, alpha=0.85, zorder=3)
    ax.set_yticks(y)
    # 左侧：排名徽章
    rank_labels = [f"No.{i+1}" for i in range(n)]
    ax.set_yticklabels(rank_labels, fontsize=10, color=TEXT_COLOR, fontweight="bold")
    ax.set_xlabel("昨日成交量（笔）", fontsize=10, color=TEXT_COLOR)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5, zorder=0)

    mx = max(counts, default=1) or 1
    # 给条形留出右侧标签空间
    ax.set_xlim(0, mx * 1.85)

    # 阈值：bar 长度需 >= 此值，藏品名才放在 bar 内（白字）；否则放 bar 外（深色字）
    inside_threshold = mx * 0.30

    for i, (bar, c, r, av, mn, nm, cat) in enumerate(
        zip(bars, counts, rates, avgs, mins, names, cats)
    ):
        truncated = nm if len(nm) <= 14 else nm[:14] + "…"
        chip = f"[{cat}] " if cat else ""
        label_text = f"{chip}{truncated}"

        # 自适应：bar 够长 → 内部白字；bar 太短 → 外部深色字
        if c >= inside_threshold:
            ax.text(mx * 0.012, y[i], label_text,
                    va="center", ha="left", fontsize=10,
                    color="white", fontweight="bold", zorder=5)
            metric_x = c + mx * 0.02
        else:
            ax.text(c + mx * 0.015, y[i], label_text,
                    va="center", ha="left", fontsize=10,
                    color=TEXT_COLOR, fontweight="bold", zorder=5)
            # 估算文字宽度后再放数据指标
            metric_x = c + mx * 0.015 + mx * (0.022 * (len(label_text) + 2))

        # 右侧指标：成交量 + 涨跌% + 均价 + 地板价
        ax.text(metric_x, y[i], f"{c:,}笔", va="center", ha="left",
                fontsize=9.5, color=TEXT_COLOR, fontweight="bold", zorder=5)
        suffix_parts = []
        if r is not None:
            arrow = "▲" if r >= 0 else "▼"
            sign = "+" if r >= 0 else ""
            suffix_parts.append(f"{arrow}{sign}{r:.1f}%")
        if av:
            suffix_parts.append(f"均价¥{av:,.0f}")
        if mn:
            suffix_parts.append(f"地板¥{mn:,.0f}")
        if suffix_parts:
            rate_color = _color(r) if r is not None else TEXT_COLOR
            suffix = "  " + "  |  ".join(suffix_parts)
            ax.text(metric_x + mx * 0.07, y[i], suffix, va="center", ha="left",
                    fontsize=9.5, color=rate_color, zorder=5)

    # 图例
    up_p = mpatches.Patch(color=_UP_COLOR, label="均价上涨 (>+0.5%)")
    dn_p = mpatches.Patch(color=_DOWN_COLOR, label="均价下跌 (<-0.5%)")
    flat_p = mpatches.Patch(color="#8c8c8c", label="持平 / 无数据")
    ax.legend(handles=[up_p, dn_p, flat_p], loc="lower right",
              fontsize=9, frameon=False)

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
    """
    板块成交量排行横向条形图（Top 8）。

    - 颜色按板块均价涨跌：红涨/绿跌/灰持平
    - Top 1~3 在条形左侧叠加金/银/铜排名徽章
    - 右侧标签：成交量 + 均价涨跌%
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not top_planes:
        return ""

    items = top_planes[:8]
    n = len(items)
    names = [p["plane_name"] for p in items]
    counts = [p.get("deal_count") or 0 for p in items]
    rates = [p.get("avg_price_rate") for p in items]

    def _color(r):
        if r is None:
            return "#8c8c8c"
        if r > 0.5:
            return _UP_COLOR
        if r < -0.5:
            return _DOWN_COLOR
        return "#8c8c8c"

    colors = [_color(r) for r in rates]
    # 顶部强调：Top1 不透明，其余 0.85
    alphas = [1.0 if i == 0 else (0.92 if i < 3 else 0.78) for i in range(n)]

    y = np.arange(n)[::-1]  # No.1 在顶
    fig, ax = plt.subplots(figsize=(10, max(4.2, n * 0.6 + 1.5)))
    setup_ax(ax, "板块成交量排行（Top 8）")

    bars = ax.barh(y, counts, 0.62, zorder=3)
    for b, c, a in zip(bars, colors, alphas):
        b.set_color(c)
        b.set_alpha(a)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=10, color=TEXT_COLOR, fontweight="bold")
    ax.set_xlabel("昨日成交量（笔）", fontsize=10, color=TEXT_COLOR)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)

    mx = max(counts, default=1) or 1
    ax.set_xlim(0, mx * 1.32)

    medals = {0: ("🥇", "#d4a017"), 1: ("🥈", "#a0a0a0"), 2: ("🥉", "#a06b3c")}
    medal_text = {0: "No.1", 1: "No.2", 2: "No.3"}

    for i, (c, r) in enumerate(zip(counts, rates)):
        # 排名徽章（条形内左侧）
        if i in medal_text:
            ax.text(mx * 0.012, y[i], medal_text[i],
                    va="center", ha="left", fontsize=10,
                    color="white", fontweight="bold", zorder=5)
        # 右侧双指标
        if r is None:
            label = f"{c:,}"
        else:
            sign = "+" if r >= 0 else ""
            arrow = "▲" if r >= 0 else "▼"
            label = f"{c:,}笔   均价{arrow}{sign}{r:.1f}%"
        rate_color = _color(r) if r is not None else TEXT_COLOR
        # 主笔数（深色）
        ax.text(c + mx * 0.015, y[i], f"{c:,}笔",
                va="center", ha="left", fontsize=9.5,
                color=TEXT_COLOR, fontweight="bold")
        if r is not None:
            ax.text(c + mx * 0.13, y[i],
                    f"均价{('▲+' if r >= 0 else '▼')}{abs(r):.1f}%",
                    va="center", ha="left", fontsize=9.5, color=rate_color)

    up_patch = mpatches.Patch(color=_UP_COLOR, label="均价上涨")
    dn_patch = mpatches.Patch(color=_DOWN_COLOR, label="均价下跌")
    flat_patch = mpatches.Patch(color="#8c8c8c", label="持平 / 无数据")
    ax.legend(handles=[up_patch, dn_patch, flat_patch],
              loc="lower right", fontsize=9, frameon=False)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_market_trend_line(
    summaries_7d: list[dict],
    output_dir: str,
    filename: str = "market_trend_line.png",
) -> str:
    """
    近7天全市场市值 & 成交量双轴折线图。

    左轴（实线 + 填充）：总市值（亿元）— 蓝
    右轴（虚线）：成交笔数 — 橙
    Annotation 错开 — 市值在点上方、成交量在点下方，避免重叠。
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not summaries_7d:
        return ""

    dates = [s["stat_date"][-5:] for s in summaries_7d]
    market_values = [(s.get("total_market_value") or 0) / 1e8 for s in summaries_7d]
    deal_counts = [s.get("total_deal_count") or 0 for s in summaries_7d]

    LEFT = COLORS[0]   # 蓝
    RIGHT = "#fa8c16"  # 橙（与蓝色对比更强，放弃绿色避免与涨跌色混淆）

    fig, ax1 = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_facecolor(BG_COLOR)
    ax1.set_facecolor(BG_COLOR)
    ax1.set_title("近 7 天市值 & 成交量趋势", fontsize=13, fontweight="bold",
                  color=TEXT_COLOR, pad=10)
    ax1.spines["top"].set_visible(False)
    ax1.spines["bottom"].set_color(GRID_COLOR)
    ax1.spines["left"].set_color(LEFT)
    ax1.spines["right"].set_visible(False)
    ax1.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax1.grid(axis="y", color=GRID_COLOR, linewidth=0.5, linestyle="--")

    # 左轴：市值（带填充）
    line1, = ax1.plot(dates, market_values, marker="o", color=LEFT,
                      linewidth=2.2, markersize=6, label="总市值（亿）", zorder=4)
    ax1.fill_between(dates, market_values, alpha=0.10, color=LEFT, zorder=2)
    ax1.set_ylabel("总市值（亿元）", fontsize=10, color=LEFT, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor=LEFT)
    if market_values:
        mv_max = max(market_values)
        ax1.set_ylim(0, mv_max * 1.18)
        for x, v in zip(dates, market_values):
            if v:
                ax1.annotate(f"{v:.2f}", (x, v), textcoords="offset points",
                             xytext=(0, 9), ha="center", fontsize=8.5,
                             color=LEFT, fontweight="bold")

    # 右轴：成交量（虚线）
    ax2 = ax1.twinx()
    ax2.set_facecolor(BG_COLOR)
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(RIGHT)
    ax2.tick_params(colors=TEXT_COLOR, labelsize=9, axis="y", labelcolor=RIGHT)
    line2, = ax2.plot(dates, deal_counts, marker="s", color=RIGHT,
                      linewidth=2, markersize=5.5, linestyle="--",
                      label="成交笔数", zorder=3)
    ax2.set_ylabel("成交笔数", fontsize=10, color=RIGHT, fontweight="bold")
    if deal_counts:
        dc_max = max(deal_counts) or 1
        ax2.set_ylim(0, dc_max * 1.20)
        for x, v in zip(dates, deal_counts):
            if v:
                ax2.annotate(f"{v:,}", (x, v), textcoords="offset points",
                             xytext=(0, -15), ha="center", fontsize=8.5,
                             color=RIGHT)

    ax1.legend(handles=[line1, line2], loc="upper left", fontsize=9,
               facecolor=BG_COLOR, labelcolor=TEXT_COLOR, frameon=False)

    fig.tight_layout()
    save_fig(fig, path)
    return path


def chart_ip_deal_rank(
    ip_snapshots: list[dict],
    output_dir: str,
    filename: str = "ip_deal_rank.png",
) -> str:
    """
    Top 5 热门 IP 成交对比（蝴蝶图 / 双向横向条形）。

    左轴：昨日成交额 ¥（蓝色）
    右轴：昨日成交笔数（按环比涨跌染色：红涨/绿跌）
    中央：排名徽章 + IP名
    右侧标签：环比 %（带方向箭头）

    ip_snapshots: [{"ip_name", "deal_count", "market_amount", "deal_count_rate"}, ...]
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not ip_snapshots:
        return ""

    items = sorted(ip_snapshots, key=lambda x: x.get("deal_count") or 0, reverse=True)[:5]
    if not items:
        return ""

    names = [i.get("ip_name") or "—" for i in items]
    counts = [i.get("deal_count") or 0 for i in items]
    amounts = [i.get("market_amount") or 0 for i in items]
    rates = [i.get("deal_count_rate") for i in items]

    n = len(items)
    y = np.arange(n)[::-1]  # 第1名在顶部
    bar_h = 0.55

    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(11, max(4.2, n * 0.85 + 1.4)),
        gridspec_kw={"width_ratios": [1, 1], "wspace": 0.55},
    )
    fig.patch.set_facecolor(BG_COLOR)
    fig.suptitle("昨日热门 IP 成交 Top 5", fontsize=14, fontweight="bold",
                 color=TEXT_COLOR, y=1.0)

    # ── 左：成交额 ¥（向左延伸） ──
    setup_ax(ax_left, "")
    ax_left.barh(y, amounts, bar_h, color=_NEUTRAL, alpha=0.85, zorder=3)
    ax_left.invert_xaxis()
    ax_left.set_yticks([])
    ax_left.set_xlabel("成交额（¥）", fontsize=10, color=TEXT_COLOR)
    ax_left.grid(axis="x", color=GRID_COLOR, linewidth=0.5)
    mx_amt = max(amounts, default=1) or 1
    for i, amt in enumerate(amounts):
        if amt <= 0:
            continue
        lbl = f"¥{amt/10000:.1f}万" if amt >= 10000 else f"¥{amt:,.0f}"
        ax_left.text(amt + mx_amt * 0.02, y[i], lbl, va="center", ha="right",
                     fontsize=9, color=TEXT_COLOR, fontweight="bold")

    # ── 右：成交笔数（按环比染色） ──
    setup_ax(ax_right, "")
    colors = []
    for r in rates:
        if r is None:
            colors.append("#8c8c8c")
        elif r >= 0:
            colors.append(_UP_COLOR)
        else:
            colors.append(_DOWN_COLOR)
    ax_right.barh(y, counts, bar_h, color=colors, zorder=3)
    ax_right.set_yticks([])
    ax_right.set_xlabel("成交笔数（笔）", fontsize=10, color=TEXT_COLOR)
    ax_right.grid(axis="x", color=GRID_COLOR, linewidth=0.5)
    mx_cnt = max(counts, default=1) or 1
    for i, (c, r) in enumerate(zip(counts, rates)):
        if c <= 0:
            continue
        if r is None:
            lbl = f"{c:,}"
        else:
            arrow = "▲" if r >= 0 else "▼"
            sign = "+" if r >= 0 else ""
            lbl = f"{c:,}  {arrow}{sign}{r:.1f}%"
        ax_right.text(c + mx_cnt * 0.02, y[i], lbl, va="center", ha="left",
                      fontsize=9, color=TEXT_COLOR, fontweight="bold")

    # ── 中央：排名徽章 + IP 名（用 figure 坐标定位于两子图之间） ──
    medals = ["No.1", "No.2", "No.3", "No.4", "No.5"]
    medal_colors = ["#d4a017", "#a0a0a0", "#a06b3c", TEXT_COLOR, TEXT_COLOR]
    fig.canvas.draw()  # 确保 axes 位置已计算
    for i, name in enumerate(names):
        l_pos = ax_left.get_position()
        r_pos = ax_right.get_position()
        cx = (l_pos.x1 + r_pos.x0) / 2
        bbox = ax_right.get_position()
        y_frac = bbox.y0 + (bbox.y1 - bbox.y0) * ((y[i] + 0.5) / n)
        medal = medals[i] if i < len(medals) else f"No.{i+1}"
        mc = medal_colors[i] if i < len(medal_colors) else TEXT_COLOR
        fig.text(cx, y_frac, f"{medal}\n{name}", ha="center", va="center",
                 fontsize=11, color=mc, fontweight="bold", linespacing=1.3)

    # 图例
    up_patch = mpatches.Patch(color=_UP_COLOR, label="成交量环比↑")
    dn_patch = mpatches.Patch(color=_DOWN_COLOR, label="成交量环比↓")
    amt_patch = mpatches.Patch(color=_NEUTRAL, label="成交额")
    fig.legend(handles=[amt_patch, up_patch, dn_patch], loc="lower center",
               ncol=3, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.0))

    fig.subplots_adjust(left=0.06, right=0.94, top=0.90, bottom=0.12, wspace=0.55)
    save_fig(fig, path)
    return path

