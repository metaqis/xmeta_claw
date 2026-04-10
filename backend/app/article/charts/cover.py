"""封面图生成 — 微信公众号首图（900×383）。

设计规范：
  - 深蓝渐变背景 + 右侧 IP 吉祥物
  - 左侧大标题 + 副标题说明
  - 底部数据来源 logo 条（xmeta + jingtan）
  - 全部通过 PIL 绘制，无 matplotlib 依赖
"""
from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .base import ensure_dir

# ── 资源路径 ─────────────────────────────────────────────
_ASSETS = Path(__file__).parent
_IP_LOGO    = _ASSETS / "ip_logo.png"
_XMETA_LOGO = _ASSETS / "xmeta_logo.png"
_JT_LOGO    = _ASSETS / "jingtan_logo.png"

# ── 尺寸 ─────────────────────────────────────────────────
W, H = 900, 383

# ── 颜色 ─────────────────────────────────────────────────
GRAD_LEFT  = (10, 20, 60)      # 深海蓝
GRAD_RIGHT = (28, 54, 120)     # 中蓝
ACCENT     = (0, 210, 255)     # 青蓝高亮
TEXT_WHITE = (255, 255, 255)
TEXT_LIGHT = (180, 210, 255)
DIVIDER    = (60, 100, 180)
LOGO_BG    = (20, 38, 90, 200) # 半透明底条


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """尝试加载系统中文字体，找不到则用默认字体。"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑 Regular
        "C:/Windows/Fonts/msyhbd.ttc",      # 微软雅黑 Bold
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    bold_candidates = [
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for p in (bold_candidates if bold else candidates):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_gradient(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """左→右深蓝渐变背景。"""
    for x in range(w):
        t = x / w
        r = int(GRAD_LEFT[0] + (GRAD_RIGHT[0] - GRAD_LEFT[0]) * t)
        g = int(GRAD_LEFT[1] + (GRAD_RIGHT[1] - GRAD_LEFT[1]) * t)
        b = int(GRAD_LEFT[2] + (GRAD_RIGHT[2] - GRAD_LEFT[2]) * t)
        draw.line([(x, 0), (x, h)], fill=(r, g, b))


def _draw_decorative_arcs(draw: ImageDraw.ImageDraw) -> None:
    """左上角装饰弧线。"""
    for i, alpha in enumerate([30, 20, 12]):
        r = 180 + i * 80
        bbox = [-r, -r, r, r]
        draw.arc(bbox, start=0, end=90,
                 fill=(*ACCENT, alpha), width=2)


def _draw_accent_line(draw: ImageDraw.ImageDraw, x: int, y0: int, y1: int) -> None:
    """标题左侧青蓝竖线装饰。"""
    draw.rectangle([x, y0, x + 5, y1], fill=ACCENT)


# 列表模式安全区：微信从中心裁取 383×383 正方形，即 x: 259~641，中心 x=450
_LIST_CROP_X0 = (W - H) // 2   # 259
_LIST_CROP_CX = W // 2          # 450
# 吉祥物放在最右侧，列表裁切区内不出现（纯装饰）
_MASCOT_CENTER_X = 810


def _place_ip_logo(canvas: Image.Image) -> None:
    """放置 IP 吉祥物：55% 高度右贴边，主体需在列表裁切区(x:641)之右。"""
    if not _IP_LOGO.exists():
        return
    logo = Image.open(_IP_LOGO).convert("RGBA")
    # 裁掉底部约 18%（含"元小二数藏"文字区域）
    crop_bottom = int(logo.height * 0.82)
    logo = logo.crop((0, 0, logo.width, crop_bottom))
    target_h = int(H * 0.55)
    ratio = target_h / logo.height
    target_w = int(logo.width * ratio)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    # 右对齐：右边留 4px
    x = W - target_w - 4
    y = H - target_h
    canvas.paste(logo, (x, y), logo)


def _place_source_logos(canvas: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """来源 logo 条：左对齐放在文字区底部。
    xmeta 图标内无文字需加标签；jingtan 图标自带"鲸探"文字不加重复标签。
    """
    logo_h = 22
    # (path, label_or_None)  label=None 表示图标自带文字
    logos_info = [
        (_XMETA_LOGO, "Xmeta"),
        (_JT_LOGO,    "鲸探"),   # jingtan 图标在小尺寸下难辨，仍显示文字
    ]

    x_cursor = _LIST_CROP_X0 + 28  # = 287，与文字左对齐
    y_center = H - 20
    small_font = _load_font(13)

    for i, (logo_path, label) in enumerate(logos_info):
        if i > 0:
            dot = "  ·  "
            draw.text((x_cursor, y_center - 8), dot, font=small_font, fill=TEXT_LIGHT)
            x_cursor += draw.textbbox((0, 0), dot, font=small_font)[2]
        if logo_path.exists():
            try:
                icon = Image.open(logo_path).convert("RGBA")
                iw = int(icon.width * logo_h / icon.height)
                icon = icon.resize((iw, logo_h), Image.LANCZOS)
                canvas.paste(icon, (x_cursor, y_center - logo_h // 2), icon)
                x_cursor += iw + 5
            except Exception:
                pass
        if label:
            bb = draw.textbbox((0, 0), label, font=small_font)
            draw.text((x_cursor, y_center - 8), label, font=small_font, fill=TEXT_LIGHT)
            x_cursor += bb[2] - bb[0]


def generate_cover(
    title: str,
    subtitle: str,
    output_dir: str,
    filename: str = "cover.png",
) -> str:
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # ① 渐变背景
    _draw_gradient(draw, W, H)

    # ② 装饰弧线（左上角）
    _draw_decorative_arcs(draw)

    # ③ 右侧 IP 吉祥物（60% 高度，右贴边，不溢出）
    _place_ip_logo(canvas)

    # ④ 半透明蒙版：列表裁切区（x:230~660）加一层深蓝底，确保文字可读
    mask = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask_draw = ImageDraw.Draw(mask, "RGBA")
    # 左侧渐入
    for x in range(230):
        alpha = int(120 * (x / 230))
        mask_draw.line([(x, 0), (x, H)], fill=(8, 16, 50, alpha))
    # 中心文字区：固定深底
    mask_draw.rectangle([230, 0, 620, H], fill=(8, 16, 50, 130))
    # 右侧渐出（620~720）
    for x in range(620, 720):
        alpha = int(130 * (1 - (x - 620) / 100))
        mask_draw.line([(x, 0), (x, H)], fill=(8, 16, 50, alpha))
    canvas = Image.alpha_composite(canvas, mask)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # ⑤ 字体 & 文字左对齐锚点（在列表裁切区内居左）
    TEXT_X = _LIST_CROP_X0 + 28  # = 287
    parts = title.split("·") if "·" in title else [title, ""]
    type_text = parts[0].strip()
    date_text = parts[1].strip() if len(parts) > 1 else ""

    font_type = _load_font(34, bold=True)
    font_date = _load_font(56, bold=True)
    font_sub  = _load_font(19)

    # ⑥ 竖线装饰（固定在 TEXT_X 左侧 12px）
    _draw_accent_line(draw, TEXT_X - 12, 82, 216)

    # 主标题两行
    draw.text((TEXT_X, 85), type_text, font=font_type, fill=TEXT_WHITE)
    if date_text:
        draw.text((TEXT_X, 128), date_text, font=font_date, fill=ACCENT)

    # ⑦ 分隔线
    draw.rectangle([TEXT_X, 228, TEXT_X + 270, 230], fill=DIVIDER)

    # ⑧ 副标题数据行
    y_sub = 242
    for seg in subtitle.split("|"):
        seg = seg.strip()
        if seg:
            draw.text((TEXT_X, y_sub), seg, font=font_sub, fill=TEXT_LIGHT)
            y_sub += 28

    # ⑨ 来源 logo（左对齐，贴底）
    _place_source_logos(canvas, draw)

    # ⑩ 转 RGB 保存
    canvas.convert("RGB").save(path, "PNG", optimize=True)
    return path
