"""藏品卡片拼图 — PIL 设计感卡片布局（当日发行总览图）。"""
import os
from io import BytesIO

import httpx
from PIL import Image, ImageDraw, ImageFont

from .base import ensure_dir

# 输出图片分辨率倍数（2 = 原始尺寸的 2 倍，微信显示更清晰）
SCALE = 2


def generate_launch_grid(
    launches: list[dict],
    output_dir: str,
    filename: str = "launch_grid.png",
) -> str:
    """
    设计感卡片布局：全局深色 header + 每发行项一张白色圆角卡片。
    左列：日历封面（圆角）+ 份数药丸徽章；右列：名称 + 彩色统计徽章 + 含品缩略图网格。
    """
    ensure_dir(output_dir)
    path = os.path.join(output_dir, filename)

    launches = [l for l in (launches or []) if l][:10]
    if not launches:
        return ""

    S = SCALE  # 分辨率倍数简写

    # ── 字体 ─────────────────────────────────────────────────
    _FONT_CANDIDATES = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]

    def _font(size: int):
        for fp in _FONT_CANDIDATES:
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # 字体尺寸全部 × S，保持逻辑键不变（FT[12] 实际是 12*S 号字）
    FT = {s: _font(s * S) for s in [10, 11, 12, 13, 14, 15, 17, 20, 22]}

    # ── 颜色系统 ─────────────────────────────────────────────
    C_BG         = (235, 239, 250)
    C_CARD       = (255, 255, 255)
    C_SHADOW1    = (195, 204, 226)
    C_SHADOW2    = (215, 221, 238)
    C_BORDER     = (218, 224, 240)
    C_ACCENT     = ( 22, 119, 255)
    C_HEADER_BG  = ( 10,  20,  55)
    C_LEFT_PANEL = (244, 247, 255)
    C_SEP        = (210, 218, 238)
    C_DARK       = ( 20,  28,  54)
    C_MID        = ( 80,  90, 122)
    C_LIGHT      = (152, 162, 192)
    C_WHITE      = (255, 255, 255)
    C_GREEN      = ( 40, 148,  10)
    BADGE_PRICE  = ((230, 242, 255), (10,  90, 220))
    BADGE_COUNT  = ((238, 241, 250), (70,  80, 115))
    BADGE_VALUE  = ((230, 252, 238), (30, 135,  60))
    BADGE_PRIO   = ((255, 247, 220), (175, 100,  0))

    # ── 尺寸系统（全部 × S） ──────────────────────────────────
    W          = 900  * S
    H_PAD      = 16   * S
    V_GAP      = 14   * S
    GLOBAL_H   = 76   * S
    STRIP_H    = 42   * S
    BODY_PAD   = 14   * S
    CARD_R     = 10   * S
    COVER_SZ   = 180  * S
    LEFT_W     = COVER_SZ + BODY_PAD * 2 + 6 * S
    THUMB_SZ   = 100  * S
    THUMB_GAP  = 8    * S
    ARCH_COLS  = 4
    THUMB_TEXT_H = 38 * S
    THUMB_CELL_H = THUMB_SZ + THUMB_TEXT_H
    CARD_W     = W - 2 * H_PAD
    right_avail = CARD_W - LEFT_W - 1 - BODY_PAD - 10 * S

    # ── 工具函数 ─────────────────────────────────────────────
    draw_tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    _img_cache: dict[str, Image.Image] = {}

    def _tw(draw, text, font):
        try:
            return int(draw.textlength(text, font=font))
        except Exception:
            return len(text) * getattr(font, "size", 8)

    def _fetch(url: str, sz: int) -> Image.Image | None:
        if not url:
            return None
        key = f"{url}@{sz}"
        if key in _img_cache:
            return _img_cache[key].copy()
        try:
            r = httpx.get(url, timeout=8, follow_redirects=True)
            im = Image.open(BytesIO(r.content)).convert("RGB")
            w0, h0 = im.size
            m = min(w0, h0)
            im = im.crop(((w0 - m) // 2, (h0 - m) // 2, (w0 + m) // 2, (h0 + m) // 2))
            im = im.resize((sz, sz), Image.LANCZOS)
            _img_cache[key] = im
            return im.copy()
        except Exception:
            return None

    def _round_paste(canvas: Image.Image, img: Image.Image, pos: tuple, radius: int = 6):
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, img.width - 1, img.height - 1], radius=radius, fill=255
        )
        canvas.paste(img, pos, mask)

    def _wrap(text: str, max_px: int, font) -> list[str]:
        lines, cur = [], ""
        for ch in text:
            test = cur + ch
            if _tw(draw_tmp, test, font) > max_px and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines or [text]

    def _badge(draw, x, y, text, ft, bg, fg, ph=6*S, pv=3*S, r=4*S):
        tw_ = _tw(draw, text, ft)
        fs  = getattr(ft, "size", 12)
        bw, bh = tw_ + ph * 2, fs + pv * 2
        draw.rounded_rectangle([x, y, x + bw - 1, y + bh - 1], radius=r, fill=bg)
        draw.text((x + ph, y + pv), text, fill=fg, font=ft)
        return bw, bh

    # ── 卡片高度估算 ─────────────────────────────────────────
    def _card_h(launch: dict) -> int:
        contain = launch.get("contain_archives") or []
        nc   = min(len(contain), ARCH_COLS * 2)
        rows = (nc + ARCH_COLS - 1) // ARCH_COLS if nc else 0
        l_h  = BODY_PAD + COVER_SZ + 8 * S + 22 * S + BODY_PAD
        r_h  = BODY_PAD
        r_h += 24 * S * 2 + 8 * S
        r_h += 20 * S + 8 * S
        if launch.get("is_priority_purchase"):
            r_h += 20 * S + 6 * S
        r_h += 18 * S + 4 * S
        if rows:
            r_h += 6 * S + 16 * S + 8 * S
            r_h += rows * THUMB_CELL_H + max(0, rows - 1) * THUMB_GAP
        r_h += BODY_PAD
        return STRIP_H + max(l_h, r_h)

    # ── 计算总画布高度 ────────────────────────────────────────
    total_h = GLOBAL_H + V_GAP
    for l in launches:
        total_h += _card_h(l) + V_GAP
    total_h += V_GAP

    canvas = Image.new("RGB", (W, total_h), C_BG)
    draw   = ImageDraw.Draw(canvas)

    # ── 全局 Header ──────────────────────────────────────────
    draw.rectangle([0, 0, W, GLOBAL_H], fill=C_HEADER_BG)
    draw.rectangle([0, 0, 6 * S, GLOBAL_H], fill=C_ACCENT)
    draw.rectangle([0, GLOBAL_H - 4 * S, W, GLOBAL_H], fill=C_ACCENT)

    n           = len(launches)
    total_count = sum(l.get("count", 0) for l in launches)
    total_val   = sum(l.get("value", 0) for l in launches)
    date_str    = (launches[0].get("sell_time", "") or "")[:10]

    draw.text((H_PAD + 12 * S, 10 * S), date_str,       fill=(130, 165, 225), font=FT[13])
    draw.text((H_PAD + 12 * S, 28 * S), "当日发行总览",  fill=C_WHITE,         font=FT[22])

    stats_str = f"共 {n} 项  ·  总量 {total_count:,} 份  ·  总价值 ¥{total_val:,.0f}"
    sw = _tw(draw, stats_str, FT[13])
    draw.text((W - sw - H_PAD - 12 * S, 34 * S), stats_str, fill=(150, 185, 240), font=FT[13])

    # ── 卡片循环 ─────────────────────────────────────────────
    cy = GLOBAL_H + V_GAP

    for launch in launches:
        ch = _card_h(launch)
        cx = H_PAD

        # 软阴影
        draw.rounded_rectangle([cx + 4 * S, cy + 4 * S, cx + CARD_W + 4 * S, cy + ch + 4 * S],
                                radius=CARD_R, fill=C_SHADOW1)
        draw.rounded_rectangle([cx + 2 * S, cy + 2 * S, cx + CARD_W + 2 * S, cy + ch + 2 * S],
                                radius=CARD_R, fill=C_SHADOW2)

        # 卡片白底
        draw.rounded_rectangle([cx, cy, cx + CARD_W, cy + ch], radius=CARD_R, fill=C_CARD)

        # 顶部色条（只圆两个上角）
        draw.rounded_rectangle([cx, cy, cx + CARD_W, cy + STRIP_H + CARD_R],
                                radius=CARD_R, fill=C_ACCENT)
        draw.rectangle([cx, cy + CARD_R, cx + CARD_W, cy + STRIP_H], fill=C_ACCENT)

        ip_name   = launch.get("ip_name") or "未知IP"
        sell_time = launch.get("sell_time") or ""
        time_str  = sell_time[11:16] if len(sell_time) >= 16 else sell_time

        draw.rectangle([cx + 12 * S, cy + 11 * S, cx + 15 * S, cy + STRIP_H - 11 * S],
                       fill=(200, 225, 255))
        draw.text((cx + 22 * S, cy + (STRIP_H - 15 * S) // 2), ip_name,
                  fill=C_WHITE, font=FT[15])

        tags = []
        if launch.get("is_priority_purchase"):
            pn = launch.get("priority_purchase_num") or 0
            tags.append(f"优先购 {pn:,}份")
        if time_str:
            tags.append(f"发售 {time_str}")
        tag_str = "  |  ".join(tags)
        if tag_str:
            tw_ = _tw(draw, tag_str, FT[13])
            draw.text((cx + CARD_W - tw_ - 14 * S, cy + (STRIP_H - 13 * S) // 2),
                      tag_str, fill=(195, 225, 255), font=FT[13])

        body_y = cy + STRIP_H

        # 左列背景
        draw.rectangle([cx, body_y, cx + LEFT_W, cy + ch], fill=C_LEFT_PANEL)
        draw.rectangle([cx + LEFT_W, body_y, cx + LEFT_W + 1, cy + ch], fill=C_SEP)

        # 封面图（水平 + 垂直居中）
        left_block_h = COVER_SZ + 8 * S + 22 * S
        body_h       = ch - STRIP_H
        v_offset     = max(0, (body_h - BODY_PAD * 2 - left_block_h) // 2)
        img_x = cx + CARD_R + (LEFT_W - CARD_R - COVER_SZ) // 2
        img_y = body_y + BODY_PAD + v_offset
        cover = _fetch(launch.get("img") or "", COVER_SZ)
        if cover:
            _round_paste(canvas, cover, (img_x, img_y), radius=8 * S)
            draw.rounded_rectangle([img_x - 1, img_y - 1, img_x + COVER_SZ, img_y + COVER_SZ],
                                   radius=8 * S, outline=C_BORDER)
        else:
            draw.rounded_rectangle([img_x, img_y, img_x + COVER_SZ - 1, img_y + COVER_SZ - 1],
                                   radius=8 * S, fill=(228, 233, 248), outline=C_BORDER)
            draw.text((img_x + 52 * S, img_y + 82 * S), "暂无图片", fill=C_LIGHT, font=FT[12])

        # 份数药丸
        count   = launch.get("count", 0)
        cnt_str = f"{count:,} 份"
        cnt_w   = _tw(draw, cnt_str, FT[13])
        pill_w  = cnt_w + 20 * S
        pill_x  = img_x + (COVER_SZ - pill_w) // 2
        pill_y  = img_y + COVER_SZ + 7 * S
        draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + 22 * S],
                               radius=11 * S, fill=C_BORDER)
        draw.text((pill_x + 10 * S, pill_y + 4 * S), cnt_str, fill=C_DARK, font=FT[13])

        # ── 右列 ─────────────────────────────────────────────
        rx = cx + LEFT_W + 1 + BODY_PAD
        ry = body_y + BODY_PAD

        launch_name = launch.get("name") or ""
        name_lines  = _wrap(launch_name, right_avail, FT[17])[:2]
        for i, line in enumerate(name_lines):
            draw.text((rx, ry + i * 25 * S), line, fill=C_DARK, font=FT[17])
        ry += len(name_lines) * 25 * S + 8 * S

        price = launch.get("price", 0)
        value = launch.get("value", 0)
        bx    = rx
        bw, bh = _badge(draw, bx, ry, f"¥{price:.2f} 发行价", FT[12], *BADGE_PRICE)
        bx += bw + 6 * S
        bw, _  = _badge(draw, bx, ry, f"{count:,} 份",        FT[12], *BADGE_COUNT)
        bx += bw + 6 * S
        _badge(draw, bx, ry, f"总值 ¥{value:,.0f}",           FT[12], *BADGE_VALUE)
        ry += bh + 8 * S

        if launch.get("is_priority_purchase"):
            pn = launch.get("priority_purchase_num") or 0
            pct_str = f"（{pn / count * 100:.0f}%）" if count else ""
            _, pb_h = _badge(draw, rx, ry, f"★ 优先购 {pn:,} 份{pct_str}",
                             FT[12], *BADGE_PRIO, ph=8 * S)
            ry += pb_h + 8 * S

        contain = launch.get("contain_archives") or []
        owners = []
        for ca in contain:
            o = ca.get("owner") or ""
            if o and o not in owners:
                owners.append(o)
        if owners:
            owner_str = "  /  ".join(owners[:3])
            label_str = "发行方："
            lw_ = _tw(draw, label_str, FT[11])
            draw.text((rx,       ry), label_str, fill=C_LIGHT, font=FT[11])
            draw.text((rx + lw_, ry), owner_str,  fill=C_MID,   font=FT[12])
            ry += 18 * S
        if contain:
            ry += 4 * S
            draw.text((rx, ry), f"包含 {len(contain)} 件藏品", fill=C_LIGHT, font=FT[11])
            ry += 16 * S
            draw.line([rx, ry, rx + right_avail, ry], fill=C_BORDER, width=S)
            ry += 8 * S

            arch_cell_w = (right_avail - (ARCH_COLS - 1) * THUMB_GAP) // ARCH_COLS

            for ci, ca in enumerate(contain[: ARCH_COLS * 2]):
                col_i = ci % ARCH_COLS
                row_i = ci // ARCH_COLS
                ax_  = rx + col_i * (arch_cell_w + THUMB_GAP)
                ay_  = ry + row_i * (THUMB_CELL_H + THUMB_GAP)

                draw.rounded_rectangle([ax_, ay_, ax_ + arch_cell_w - 1, ay_ + THUMB_SZ - 1],
                                       radius=6 * S, fill=(232, 236, 250))

                thumb_ox = (arch_cell_w - THUMB_SZ) // 2
                thumb = _fetch(ca.get("archive_img") or "", THUMB_SZ)
                if thumb:
                    _round_paste(canvas, thumb, (ax_ + thumb_ox, ay_), radius=6 * S)
                    draw.rounded_rectangle(
                        [ax_ + thumb_ox, ay_,
                         ax_ + thumb_ox + THUMB_SZ - 1, ay_ + THUMB_SZ - 1],
                        radius=6 * S, outline=C_BORDER)

                pct = ca.get("percentage") or 0
                if pct:
                    ps  = f"{pct:.0f}%"
                    ptw = _tw(draw, ps, FT[10])
                    pw  = ptw + 8 * S
                    px0 = ax_ + arch_cell_w - pw - 2 * S
                    draw.rounded_rectangle([px0, ay_ + 2 * S, px0 + pw - 1, ay_ + 17 * S],
                                           radius=4 * S, fill=C_ACCENT)
                    draw.text((px0 + 4 * S, ay_ + 3 * S), ps, fill=C_WHITE, font=FT[10])

                a_name  = ca.get("archive_name") or ""
                a_lines = _wrap(a_name, arch_cell_w - 4 * S, FT[11])[:1]
                name_txt = a_lines[0] if a_lines else a_name
                ntw = _tw(draw, name_txt, FT[11])
                draw.text((ax_ + max(0, (arch_cell_w - ntw) // 2), ay_ + THUMB_SZ + 4 * S),
                          name_txt, fill=C_DARK, font=FT[11])

                mp   = ca.get("live_min_price") or ca.get("min_price") or 0
                deal = ca.get("deal_count") or 0
                sell = ca.get("live_total") or ca.get("selling_count") or 0
                if mp:
                    price_txt = f"¥{mp:.1f}"
                    deal_txt  = f" 成交{deal}" if deal else (f" 售{sell}" if sell else "")
                    ptw_ = _tw(draw, price_txt, FT[11])
                    dtw_ = _tw(draw, deal_txt,  FT[11]) if deal_txt else 0
                    full_w = ptw_ + dtw_
                    mx = ax_ + max(0, (arch_cell_w - full_w) // 2)
                    draw.text((mx,         ay_ + THUMB_SZ + 20 * S), price_txt, fill=C_GREEN, font=FT[11])
                    if deal_txt:
                        draw.text((mx + ptw_, ay_ + THUMB_SZ + 20 * S), deal_txt, fill=C_MID, font=FT[11])
                else:
                    sn = ca.get("sales_num") or 0
                    if sn:
                        sn_txt = f"{sn:,}份"
                        snw = _tw(draw, sn_txt, FT[11])
                        draw.text((ax_ + max(0, (arch_cell_w - snw) // 2), ay_ + THUMB_SZ + 20 * S),
                                  sn_txt, fill=C_MID, font=FT[11])

        cy += ch + V_GAP

    canvas.save(path, "PNG", quality=95)
    return path
