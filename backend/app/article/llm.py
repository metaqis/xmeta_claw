"""LLM 文章生成器 — 通过报告技能注册表调用 LLM 生成文章内容。

所有报告类型子包必须在此处导入以触发 @register 装饰器。
"""
from typing import Any

from loguru import logger

from app.agent.llm import client
from app.core.config import get_settings

# 触发技能注册（顺序无关，均注册到全局 _REGISTRY）
import app.article.reports.daily    # noqa: F401
import app.article.reports.weekly   # noqa: F401
import app.article.reports.monthly  # noqa: F401

from app.article.reports import get_skill
from app.article.reports.daily.prompt import SYSTEM_PROMPT

settings = get_settings()


async def generate_article_content(
    article_type: str,
    data: dict[str, Any],
    available_charts: list[str],
) -> dict[str, str]:
    """调用 LLM 生成文章，返回 {title, markdown, summary}。"""
    skill = get_skill(article_type)
    user_prompt = skill.build_prompt(data, available_charts)

    logger.info(f"开始生成 {article_type} 文章, 数据键: {list(data.keys())}")

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=0.4,
    )
    content = response.choices[0].message.content or ""

    # 提取标题
    title = ""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break

    if not title:
        type_names = {"daily": "数藏日报", "weekly": "数藏周报", "monthly": "数藏月报"}
        date_label = data.get("date") or data.get("start_date") or data.get("month_label", "")
        title = f"{type_names.get(article_type, '数藏分析')} · {date_label}"

    summary_resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "请用一句话（不超过100字）概括以下文章的核心内容，作为微信公众号文章的摘要。",
            },
            {"role": "user", "content": content[:3000]},
        ],
        max_tokens=200,
        temperature=0.2,
    )
    summary = (summary_resp.choices[0].message.content or "").strip()[:200]

    return {"title": title, "markdown": content, "summary": summary}
