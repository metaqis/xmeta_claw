"""Markdown → 微信公众号 HTML 渲染器。"""
import re


def markdown_to_wechat_html(markdown_text: str, chart_urls: dict[str, str]) -> str:
    """将 Markdown 转换为微信公众号兼容的 HTML（内联样式）。

    图表替换规则：
      - `![alt](CHART:key)` 命中且 chart_urls 中有对应 URL → 替换为 <img>
      - 命中但 URL 缺失 → 整行（含尾部"← 若可用"等说明文字）一并删除，避免出现孤立提示
    """
    import markdown as md

    def _replace_chart_line(m):
        key = m.group(1)
        url = chart_urls.get(key, "")
        if url:
            return f'<img src="{url}" style="width:100%;border-radius:8px;margin:16px 0;" />'
        return ""  # 整行删除，连同前后缀文字

    # 先处理整行 ![..](CHART:xx)  ← 若可用 类的占位行（带前后说明文字）
    text = re.sub(
        r"^[ \t]*!\[[^\]]*\]\(CHART:(\w+)\)[^\n]*\n?",
        _replace_chart_line,
        markdown_text,
        flags=re.MULTILINE,
    )
    # 再处理行内零散的 CHART 占位（兜底）
    text = re.sub(r"!\[[^\]]*\]\(CHART:(\w+)\)", _replace_chart_line, text)

    html = md.markdown(text, extensions=["tables", "nl2br"])

    style_map = {
        "<h1>": '<h1 style="font-size:22px;font-weight:bold;color:#1a1a2e;border-bottom:2px solid #1677ff;padding-bottom:8px;margin:24px 0 16px;">',
        "<h2>": '<h2 style="font-size:20px;font-weight:bold;color:#1a1a2e;border-left:4px solid #1677ff;padding-left:12px;margin:24px 0 12px;">',
        "<h3>": '<h3 style="font-size:17px;font-weight:bold;color:#333;margin:20px 0 10px;">',
        "<p>":  '<p style="font-size:15px;color:#333;line-height:1.8;margin:10px 0;">',
        "<table>": '<table style="width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;">',
        "<th>": '<th style="background:#f0f5ff;color:#1a1a2e;padding:8px 10px;border:1px solid #e8e8e8;text-align:left;font-weight:600;">',
        "<td>": '<td style="padding:8px 10px;border:1px solid #e8e8e8;color:#333;">',
        "<tr>": '<tr style="background:#fff;">',
        # <strong> 保持黑色加粗，不染主题蓝（避免正文里所有数据都变蓝色，视觉过于跳）
        "<strong>": '<strong style="color:#1a1a2e;font-weight:600;">',
        "<blockquote>": '<blockquote style="border-left:4px solid #1677ff;padding:12px 16px;margin:16px 0;background:#f0f5ff;color:#555;font-size:14px;">',
        "<ul>": '<ul style="padding-left:20px;margin:10px 0;">',
        "<ol>": '<ol style="padding-left:20px;margin:10px 0;">',
        "<li>": '<li style="font-size:15px;color:#333;line-height:1.8;margin:4px 0;">',
        "<hr>": '<hr style="border:none;border-top:1px solid #e8e8e8;margin:24px 0;" />',
        "<hr />": '<hr style="border:none;border-top:1px solid #e8e8e8;margin:24px 0;" />',
    }
    for tag, styled in style_map.items():
        html = html.replace(tag, styled)

    # 表格外包一层支持移动端横向滚动的容器，防止长表格在微信端撑破布局
    html = re.sub(
        r"(<table[^>]*>.*?</table>)",
        r'<section style="overflow-x:auto;-webkit-overflow-scrolling:touch;">\1</section>',
        html,
        flags=re.DOTALL,
    )

    wrapper = (
        '<section style="max-width:600px;margin:0 auto;padding:20px;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,\'Helvetica Neue\',Arial,sans-serif;'
        'color:#333;line-height:1.8;">'
        f"{html}"
        '<section style="text-align:center;padding:20px 0;margin-top:24px;'
        'border-top:1px solid #e8e8e8;color:#999;font-size:12px;">'
        "数据来源：xmeta与鲸探平台 | 文章由AI和相关skill自动生成"
        "</section>"
        "</section>"
    )
    return wrapper
