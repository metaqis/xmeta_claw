"""图表基础设施 — matplotlib 配置、调色板、公用辅助函数。"""
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ── 中文字体配置 ──────────────────────────────────────────────────────────
# 策略1：直接用字体文件路径注册（最可靠，适用于 macOS/Linux）
# 策略2：退化到 font.sans-serif 列表匹配（适用于 Windows / 已安装中文字体）
_CJK_FONT_PATHS = [
    # macOS 系统字体（STHeiti / PingFang 私有字体用 .ttc 文件）
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    # Windows 系统字体
    "C:/Windows/Fonts/msyh.ttc",        # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",      # 微软雅黑 Bold
    "C:/Windows/Fonts/simhei.ttf",      # 黑体
    "C:/Windows/Fonts/simsun.ttc",      # 宋体
    # Linux 常见中文字体
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # 项目内自带字体（放在 backend/static/fonts/ 下可跨平台）
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "fonts", "NotoSansSC-Regular.ttf"),
]

_cjk_font_prop = None  # 全局字体属性对象，供图表函数直接传入
for _fp in _CJK_FONT_PATHS:
    if os.path.exists(_fp):
        try:
            fm.fontManager.addfont(_fp)
            _prop = fm.FontProperties(fname=_fp)
            # 写入 rcParams，让所有文本元素默认使用该字体
            matplotlib.rcParams["font.sans-serif"] = [_prop.get_name(), "sans-serif"]
            matplotlib.rcParams["font.family"] = "sans-serif"
            _cjk_font_prop = _prop
            break
        except Exception:
            continue

matplotlib.rcParams["axes.unicode_minus"] = False  # 防止负号变方块

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
