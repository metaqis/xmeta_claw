"""Markdown → 微信公众号 HTML 渲染器（数藏科技风格版）。

设计主题：「数字资产情报」 — 专业金融数据 × 数藏科技感
颜色系统：
  深夜蓝  #0c1a2e   — 主背景/H1/表头
  电光蓝  #1e5bdc   — 主交互色/H2边条/strong
  青蓝    #06b6d4   — 次强调/H3/列表
  文字黑  #1e293b   — 正文
  灰蓝    #64748b   — 辅助/blockquote
  边框    #e2e8f0   — 分隔线

WeChat 内联样式约束：
  ✓ linear-gradient / border-radius / box-shadow / flex
  ✗ ::before/::after / CSS 变量 / clip-path / 外部字体
"""
import re

# ── 颜色常量 ────────────────────────────────────────────────────────────────
_DARK    = "#0c1a2e"
_BLUE    = "#1e5bdc"
_CYAN    = "#06b6d4"
_TEXT    = "#1e293b"
_MUTED   = "#64748b"
_BORDER  = "#e2e8f0"
_BG_SOFT = "#f0f6ff"


def markdown_to_wechat_html(markdown_text: str, chart_urls: dict[str, str]) -> str:
    """Markdown → 微信公众号增强版 HTML（全内联样式）。"""
    import markdown as md

    # ── 1. 图表占位符 ────────────────────────────────────────────────────────
    def _replace_chart(m: re.Match) -> str:
        key = m.group(1)
        url = chart_urls.get(key, "")
        if not url:
            return ""
        return (
            f'<section style="margin:20px 0;text-align:center;">'
            f'<img src="{url}" style="width:100%;max-width:600px;'
            f'display:block;margin:0 auto;border-radius:10px;'
            f'box-shadow:0 4px 18px rgba(30,91,220,0.15);" />'
            f'</section>'
        )

    text = re.sub(
        r"^[ \t]*!\[[^\]]*\]\(CHART:(\w+)\)[^\n]*\n?",
        _replace_chart, markdown_text, flags=re.MULTILINE,
    )
    text = re.sub(r"!\[[^\]]*\]\(CHART:(\w+)\)", _replace_chart, text)

    # ── 2. Markdown → HTML ───────────────────────────────────────────────────
    html = md.markdown(text, extensions=["tables", "nl2br"])

    # ── 3. 元素样式映射 ──────────────────────────────────────────────────────
    style_map = {

        # H1 ── 深夜渐变横幅，底部青蓝发光条
        "<h1>": (
            f'<h1 style="'
            f'font-size:20px;font-weight:800;color:#fff;'
            f'background:linear-gradient(135deg,{_DARK} 0%,#0f2d5e 55%,#1e4fa8 100%);'
            f'padding:20px 22px 18px;border-radius:12px;'
            f'margin:0 0 22px;letter-spacing:0.5px;line-height:1.5;'
            f'border-bottom:3px solid {_CYAN};'
            f'box-shadow:0 6px 24px rgba(30,91,220,0.30);">'
        ),

        # H2 ── 左侧电光蓝色条 + 半透明渐变背景
        "<h2>": (
            f'<h2 style="'
            f'font-size:17px;font-weight:700;color:{_DARK};'
            f'border-left:5px solid {_BLUE};'
            f'background:linear-gradient(90deg,rgba(219,234,254,0.7) 0%,rgba(255,255,255,0) 80%);'
            f'padding:11px 16px;border-radius:0 8px 8px 0;'
            f'margin:30px 0 14px;">'
        ),

        # H3 ── 左侧青蓝细条，轻量
        "<h3>": (
            f'<h3 style="'
            f'font-size:15px;font-weight:600;color:{_TEXT};'
            f'border-left:3px solid {_CYAN};'
            f'padding-left:10px;margin:22px 0 10px;">'
        ),

        # 正文段落
        "<p>": (
            f'<p style="font-size:15px;color:{_TEXT};line-height:1.95;margin:10px 0;">'
        ),

        # 表格（行样式在 _alternate_rows 中交替处理）
        "<table>": (
            f'<table style="width:100%;border-collapse:collapse;'
            f'font-size:13px;margin:0;">'
        ),
        "<th>": (
            f'<th style="'
            f'background:linear-gradient(90deg,{_DARK} 0%,#1a3a6e 100%);'
            f'color:#e0f0ff;padding:10px 12px;text-align:left;'
            f'font-weight:600;font-size:13px;white-space:nowrap;">'
        ),
        "<td>": (
            f'<td style="padding:9px 12px;'
            f'border-bottom:1px solid {_BORDER};'
            f'color:{_TEXT};font-size:13px;vertical-align:top;">'
        ),
        # <tr> 统一白底，_alternate_rows 会覆盖偶数行
        "<tr>": '<tr style="background:#fff;">',

        # strong ── 电光蓝高亮关键数据
        "<strong>": (
            f'<strong style="color:{_BLUE};font-weight:700;">'
        ),

        # blockquote ── 数据免责声明卡片，克制低调
        "<blockquote>": (
            f'<blockquote style="'
            f'border-left:3px solid #94a3b8;'
            f'padding:11px 16px;margin:24px 0;'
            f'background:#f8fafc;color:{_MUTED};'
            f'font-size:13px;border-radius:0 8px 8px 0;'
            f'line-height:1.7;">'
        ),

        # 无序列表 ── 标准 disc bullet
        "<ul>": (
            f'<ul style="padding-left:22px;margin:12px 0;">'
        ),
        "<ol>": (
            f'<ol style="padding-left:22px;margin:12px 0;">'
        ),
        "<li>": (
            f'<li style="'
            f'font-size:15px;color:{_TEXT};line-height:1.85;'
            f'margin:5px 0;">'
        ),

        # 分隔线 ── 渐变淡出
        "<hr>": (
            f'<hr style="border:none;height:1px;'
            f'background:linear-gradient(90deg,{_BLUE},transparent);'
            f'margin:28px 0;" />'
        ),
        "<hr />": (
            f'<hr style="border:none;height:1px;'
            f'background:linear-gradient(90deg,{_BLUE},transparent);'
            f'margin:28px 0;" />'
        ),
    }

    for tag, styled in style_map.items():
        html = html.replace(tag, styled)

    # ── 4. 表格行间色交替 ────────────────────────────────────────────────────
    html = _alternate_rows(html)

    # ── 5. H3 段落卡片化（每个 H3 + 其内容包成一张卡片）────────────────────
    html = _wrap_h3_cards(html)

    # ── 6. 表格外包滚动容器（移动端防撑破 + 卡片边框）────────────────────────
    html = re.sub(
        r"(<table[^>]*>.*?</table>)",
        (
            r'<section style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
            r'margin:16px 0;border-radius:10px;'
            r'border:1px solid #e2e8f0;'
            r'box-shadow:0 2px 12px rgba(30,91,220,0.08);">\1</section>'
        ),
        html,
        flags=re.DOTALL,
    )

    # ── 7. 页脚品牌条 ────────────────────────────────────────────────────────
    footer = (
        f'<section style="'
        f'margin-top:36px;padding:16px 20px;'
        f'background:linear-gradient(135deg,{_DARK} 0%,#0f2d5e 100%);'
        f'border-radius:10px;text-align:center;'
        f'box-shadow:0 4px 16px rgba(12,26,46,0.25);">'
        f'<p style="color:#7db8ff;font-size:12px;margin:0 0 4px;letter-spacing:0.5px;">'
        f'XMETA · 数字资产情报</p>'
        f'<p style="color:#475569;font-size:11px;margin:0;line-height:1.6;">'
        f'数据来源：xmeta与鲸探平台 &nbsp;|&nbsp; AI 辅助生成<br/>'
        f'内容仅供参考，不构成投资建议</p>'
        f'</section>'
    )

    # ── 7. 最外层容器（浅蓝玻璃渐变背景）────────────────────────────────────
    return (
        f'<section style="'
        f'max-width:620px;margin:0 auto;padding:20px 16px;'
        f'font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\','
        f'\'Hiragino Sans GB\',\'Microsoft YaHei\',sans-serif;'
        f'color:{_TEXT};line-height:1.8;'
        # 三层叠加：极浅蓝底色 + 对角渐变光晕 + 顶部高光带，模拟玻璃质感
        f'background:'
        f'linear-gradient(160deg,rgba(219,234,254,0.55) 0%,rgba(255,255,255,0) 45%),'
        f'linear-gradient(340deg,rgba(186,230,253,0.35) 0%,rgba(255,255,255,0) 50%),'
        f'#f0f6ff;'
        f'border:1px solid rgba(147,197,253,0.4);'
        f'border-radius:16px;">'
        f'{html}'
        f'{footer}'
        f'</section>'
    )


def _alternate_rows(html: str) -> str:
    """对每张表的 tbody 行做奇白偶浅蓝交替。"""
    def _process_table(m: re.Match) -> str:
        count: list[int] = [0]

        def _alt_tr(tr_m: re.Match) -> str:
            count[0] += 1
            return f'<tr style="background:{bg};">'

        def _process_tbody(tb_m: re.Match) -> str:
            count[0] = 0
            return re.sub(r'<tr style="background:#fff;">', _alt_tr, tb_m.group(0))

        return re.sub(r"<tbody>.*?</tbody>", _process_tbody, m.group(0), flags=re.DOTALL)

    return re.sub(r"<table.*?</table>", _process_table, html, flags=re.DOTALL)


def _wrap_h3_cards(html: str) -> str:
    """将每个 H3 段（H3 标题 + 其后续内容，直到下一个 H2/H3 或文末）包裹为卡片。

    效果：
      - 「重点藏品解读」每件藏品 → 独立卡片
      - 「IP与发行商分析」每个 IP → 独立卡片
      - 「昨日行情复盘」各子节 → 独立卡片
    卡片样式：白底、蓝调边框、圆角、淡蓝左侧强调条、轻阴影
    """
    _CARD = (
        "background:rgba(255,255,255,0.75);"  # 半透明白，底层玻璃蓝透出
        "border:1px solid rgba(147,197,253,0.5);"
        "border-left:4px solid #06b6d4;"
        "border-radius:0 12px 12px 0;"
        "padding:16px 18px;"
        "margin:12px 0;"
        "box-shadow:0 2px 16px rgba(30,91,220,0.06);"
    )

    # 按 h2/h3 边界拆分（lookahead 保留标签本身）
    segments = re.split(r"(?=<h[23]\b)", html)
    out: list[str] = []
    for seg in segments:
        if seg.startswith("<h3"):
            out.append(f'<section style="{_CARD}">{seg}</section>')
        else:
            out.append(seg)
    return "".join(out)
