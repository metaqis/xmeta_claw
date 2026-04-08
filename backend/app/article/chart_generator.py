"""图表生成模块 — 使用 matplotlib 生成文章配图"""

import os
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 尝试使用中文字体
for font_name in ["Microsoft YaHei", "SimHei", "PingFang SC", "WenQuanYi Micro Hei"]:
    if any(font_name in f.name for f in fm.fontManager.ttflist):
        matplotlib.rcParams["font.sans-serif"] = [font_name, "sans-serif"]
        break
matplotlib.rcParams["axes.unicode_minus"] = False

# 主色板
COLORS = ["#1677ff", "#52c41a", "#faad14", "#ff4d4f", "#722ed1",
           "#13c2c2", "#eb2f96", "#fa8c16", "#2f54eb", "#a0d911"]
BG_COLOR = "#ffffff"
TEXT_COLOR = "#333333"
GRID_COLOR = "#f0f0f0"


def _setup_ax(ax, title: str = ""):
    ax.set_facecolor(BG_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.5)
    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", color=TEXT_COLOR, pad=12)


def _save(fig, path: str):
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)


def _ensure_dir(output_dir: str):
    Path(output_dir).mkdir(parents=True, exist_ok=True)


# ---------- 柱状图: 每日发行数量趋势 ----------

def chart_daily_trend(trend: list[dict], output_dir: str, filename: str = "daily_trend.png") -> str:
    _ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not trend:
        return ""

    dates = [d["date"][-5:] for d in trend]  # MM-DD
    counts = [d["count"] for d in trend]

    fig, ax = plt.subplots(figsize=(8, 4))
    _setup_ax(ax, "日发行数量趋势")
    bars = ax.bar(dates, counts, color=COLORS[0], width=0.6, zorder=3)
    for bar, c in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                str(c), ha="center", va="bottom", fontsize=9, color=TEXT_COLOR)
    ax.set_ylabel("发行数量", fontsize=10, color=TEXT_COLOR)
    _save(fig, path)
    return path


# ---------- 饼图: 平台分布 ----------

def chart_platform_pie(distribution: list[dict], output_dir: str,
                       filename: str = "platform_pie.png") -> str:
    _ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not distribution:
        return ""

    labels = [d["name"] for d in distribution]
    values = [d["count"] for d in distribution]

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.set_facecolor(BG_COLOR)
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        colors=COLORS[:len(labels)], startangle=90,
        textprops={"fontsize": 10, "color": TEXT_COLOR},
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color("#ffffff")
    ax.set_title("平台分布", fontsize=13, fontweight="bold", color=TEXT_COLOR, pad=12)
    _save(fig, path)
    return path


# ---------- 横向条形: IP 排行 ----------

def chart_ip_ranking(ranking: list[dict], output_dir: str,
                     filename: str = "ip_ranking.png") -> str:
    _ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not ranking:
        return ""

    names = [r["name"][:12] for r in reversed(ranking)]
    counts = [r["count"] for r in reversed(ranking)]

    fig, ax = plt.subplots(figsize=(7, max(3, len(names) * 0.5)))
    _setup_ax(ax, "IP 发行排行")
    bars = ax.barh(names, counts, color=COLORS[0], height=0.6, zorder=3)
    for bar, c in zip(bars, counts):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
                str(c), ha="left", va="center", fontsize=9, color=TEXT_COLOR)
    ax.set_xlabel("发行次数", fontsize=10, color=TEXT_COLOR)
    _save(fig, path)
    return path


# ---------- 折线图: 每日发行总价值趋势 ----------

def chart_value_trend(trend: list[dict], output_dir: str,
                      filename: str = "value_trend.png") -> str:
    _ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not trend:
        return ""

    dates = [d["date"][-5:] for d in trend]
    values = [d["value"] / 10000 for d in trend]  # 万元

    fig, ax = plt.subplots(figsize=(8, 4))
    _setup_ax(ax, "发行总价值趋势（万元）")
    ax.plot(dates, values, marker="o", color=COLORS[0], linewidth=2, markersize=5, zorder=3)
    ax.fill_between(dates, values, alpha=0.1, color=COLORS[0])
    for i, v in enumerate(values):
        if v > 0:
            ax.text(i, v + max(values) * 0.03, f"{v:.1f}", ha="center",
                    fontsize=8, color=TEXT_COLOR)
    ax.set_ylabel("万元", fontsize=10, color=TEXT_COLOR)
    _save(fig, path)
    return path


# ---------- 周度分组柱状图 ----------

def chart_weekly_breakdown(weeks: list[dict], output_dir: str,
                           filename: str = "weekly_breakdown.png") -> str:
    _ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)
    if not weeks:
        return ""

    labels = [f"第{w['week']}周\n{w['start']}-{w['end']}" for w in weeks]
    launches = [w["launches"] for w in weeks]
    values = [w["value"] / 10000 for w in weeks]

    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    _setup_ax(ax1, "月度各周发行概况")
    x = range(len(labels))
    w = 0.35
    bars = ax1.bar([i - w / 2 for i in x], launches, w, label="发行数", color=COLORS[0], zorder=3)
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
    _save(fig, path)
    return path


# ---------- 封面图 ----------

def generate_cover(title: str, subtitle: str, output_dir: str,
                   filename: str = "cover.png") -> str:
    _ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)

    fig, ax = plt.subplots(figsize=(9, 3.83))  # WeChat 900x383 ratio
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # 渐变背景
    gradient = plt.cm.Blues
    import numpy as np
    img = np.linspace(0, 1, 256).reshape(1, -1)
    ax.imshow(img, aspect="auto", cmap=gradient, extent=[0, 1, 0, 1], alpha=0.3, zorder=0)
    fig.patch.set_facecolor("#f0f5ff")

    ax.text(0.5, 0.6, title, ha="center", va="center",
            fontsize=26, fontweight="bold", color="#1a1a2e", zorder=2)
    ax.text(0.5, 0.32, subtitle, ha="center", va="center",
            fontsize=14, color="#555555", zorder=2)
    ax.text(0.5, 0.12, "鲸探数据平台 · 自动生成", ha="center", va="center",
            fontsize=10, color="#999999", zorder=2)

    _save(fig, path)
    return path


# ---------- 综合调用入口 ----------

def generate_daily_charts(data: dict, output_dir: str) -> dict[str, str]:
    charts: dict[str, str] = {}
    p = chart_daily_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["daily_trend"] = p
    p = chart_platform_pie(data.get("platform_distribution", []), output_dir)
    if p:
        charts["platform_pie"] = p
    ips = data.get("ip_distribution", [])
    if ips:
        p = chart_ip_ranking(ips, output_dir, "ip_distribution.png")
        if p:
            charts["ip_distribution"] = p
    p = chart_value_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["value_trend"] = p
    p = generate_cover(
        f"数藏日报 · {data['date']}",
        f"共 {data['total_launches']} 项发行 | 总量 {data['total_supply']:,} | 总价值 ¥{data['total_value']:,.0f}",
        output_dir,
    )
    if p:
        charts["cover"] = p
    return charts


def generate_weekly_charts(data: dict, output_dir: str) -> dict[str, str]:
    charts: dict[str, str] = {}
    p = chart_daily_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["daily_trend"] = p
    p = chart_platform_pie(data.get("platform_distribution", []), output_dir)
    if p:
        charts["platform_pie"] = p
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


def generate_monthly_charts(data: dict, output_dir: str) -> dict[str, str]:
    charts: dict[str, str] = {}
    p = chart_daily_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["daily_trend"] = p
    p = chart_platform_pie(data.get("platform_distribution", []), output_dir)
    if p:
        charts["platform_pie"] = p
    p = chart_ip_ranking(data.get("ip_ranking", []), output_dir)
    if p:
        charts["ip_ranking"] = p
    p = chart_value_trend(data.get("daily_trend", []), output_dir)
    if p:
        charts["value_trend"] = p
    p = chart_weekly_breakdown(data.get("weekly_breakdown", []), output_dir)
    if p:
        charts["weekly_breakdown"] = p
    p = generate_cover(
        f"数藏月报 · {data['month_label']}",
        f"共 {data['total_launches']} 项发行 | 总量 {data['total_supply']:,} | 总价值 ¥{data['total_value']:,.0f}",
        output_dir,
    )
    if p:
        charts["cover"] = p
    return charts
