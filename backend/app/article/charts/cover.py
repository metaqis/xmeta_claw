"""封面图生成 — 微信公众号首图（900×383 比例）。"""
import os

import matplotlib.pyplot as plt

from .base import save_fig, ensure_dir


def generate_cover(
    title: str,
    subtitle: str,
    output_dir: str,
    filename: str = "cover.png",
) -> str:
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)

    fig, ax = plt.subplots(figsize=(9, 3.83))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    import numpy as np
    img = np.linspace(0, 1, 256).reshape(1, -1)
    ax.imshow(img, aspect="auto", cmap=plt.cm.Blues, extent=[0, 1, 0, 1], alpha=0.3, zorder=0)
    fig.patch.set_facecolor("#f0f5ff")

    ax.text(0.5, 0.6, title, ha="center", va="center",
            fontsize=26, fontweight="bold", color="#1a1a2e", zorder=2)
    ax.text(0.5, 0.32, subtitle, ha="center", va="center",
            fontsize=14, color="#555555", zorder=2)
    ax.text(0.5, 0.12, "鲸探数据平台 · 自动生成", ha="center", va="center",
            fontsize=10, color="#999999", zorder=2)

    save_fig(fig, path)
    return path
