"""图表基础设施 — matplotlib 配置、调色板、公用辅助函数。"""
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

for _font_name in ["Microsoft YaHei", "SimHei", "PingFang SC", "WenQuanYi Micro Hei"]:
    if any(_font_name in f.name for f in fm.fontManager.ttflist):
        matplotlib.rcParams["font.sans-serif"] = [_font_name, "sans-serif"]
        break
matplotlib.rcParams["axes.unicode_minus"] = False

COLORS = [
    "#1677ff", "#52c41a", "#faad14", "#ff4d4f", "#722ed1",
    "#13c2c2", "#eb2f96", "#fa8c16", "#2f54eb", "#a0d911",
]
BG_COLOR = "#ffffff"
TEXT_COLOR = "#333333"
GRID_COLOR = "#f0f0f0"


def setup_ax(ax, title: str = "") -> None:
    ax.set_facecolor(BG_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.5)
    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", color=TEXT_COLOR, pad=12)


def save_fig(fig, path: str) -> None:
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)


def ensure_dir(output_dir: str) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
