"""LLM 文章生成器 — 通过报告技能注册表调用 LLM 生成文章内容。

两阶段生成流程（日报专用，周报/月报直接进入阶段2）：
  阶段1 — 数据核实（_phase1_extract_facts）
           用极低温度(0.1)让 LLM 从原始数据提取 JSON 事实，预算溢价率/环比等指标。
           目的：消除阶段2写作时自行推算造成的数值幻觉。
  阶段2 — 文章撰写（generate_article_content 主体）
           将阶段1 JSON 嵌入 prompt，以较低温度(0.3)撰写文章，要求严格引用已核实数字。

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


async def _phase1_extract_facts(data: dict[str, Any]) -> str:
    """
    第一阶段：数据核实与事实提取（仅日报使用）。

    通过极低温度（0.1）调用 LLM，要求其只从原始数据中提取事实并以 JSON 输出，
    不做任何推断或创作。输出的 JSON 会被嵌入第二阶段 prompt 的顶部，
    作为「已核实数据事实」供文章撰写时引用，防止 LLM 自行计算出错误数字。

    失败时返回空字符串（不中断流程，阶段2将仍用原始数据）。
    """
    # 延迟导入，避免循环依赖
    from app.article.reports.daily.prompt import ANALYSIS_SYSTEM_PROMPT, build_analysis_prompt

    user_prompt = build_analysis_prompt(data)
    logger.info("第一阶段：开始数据核实与事实提取")

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2000,
            temperature=0.1,   # 极低温度：确保输出严格忠实于原始数据，不做发挥
        )
        result = (response.choices[0].message.content or "").strip()
        logger.info(f"第一阶段完成，核实事实 JSON 长度: {len(result)} 字符")
        return result
    except Exception as e:
        # 阶段1失败不阻断流程，记录警告后继续使用原始数据
        logger.warning(f"第一阶段数据核实失败（将使用原始数据继续）: {e}")
        return ""


async def generate_article_content(
    article_type: str,
    data: dict[str, Any],
    available_charts: list[str],
) -> dict[str, str]:
    """
    调用 LLM 生成文章，返回 {title, markdown, summary}。

    日报采用两阶段生成（详见模块文档）；周报/月报直接进入第二阶段。
    """
    skill = get_skill(article_type)

    # ── 阶段1（仅日报）：数据核实 ───────────────────────────────────────────
    # 将核实结果注入到 data 副本，供 build_daily_prompt 嵌入 prompt 顶部
    enriched_data = dict(data)  # 浅拷贝，不污染原始 data
    if article_type == "daily":
        verified_facts = await _phase1_extract_facts(data)
        if verified_facts:
            # 注入已核实的 JSON 事实；build_daily_prompt 会读取 _verified_facts 键
            enriched_data["_verified_facts"] = verified_facts

    # ── 阶段2：文章撰写 ──────────────────────────────────────────────────────
    user_prompt = skill.build_prompt(enriched_data, available_charts)
    logger.info(f"第二阶段：开始生成 {article_type} 文章，数据键: {list(enriched_data.keys())}")

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=0.2,   # 低温度：确保输出克制专业，减少夸张性表达和数值发挥
    )
    content = response.choices[0].message.content or ""

    # 提取文章标题（第一个以 # 开头的行）
    title = ""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break

    if not title:
        # 兜底标题（LLM 未按格式输出时使用）
        type_names = {"daily": "数藏日报", "weekly": "数藏周报", "monthly": "数藏月报"}
        date_label = data.get("date") or data.get("start_date") or data.get("month_label", "")
        title = f"{type_names.get(article_type, '数藏分析')} · {date_label}"

    # ── 摘要生成（第三次 LLM 调用，轻量）──────────────────────────────────────
    summary_resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "请用一句话（不超过100字）概括以下文章的核心内容，作为微信公众号文章的摘要。仅输出摘要本身，不要任何前缀。",
            },
            {"role": "user", "content": content[:3000]},
        ],
        max_tokens=200,
        temperature=0.2,
    )
    summary = (summary_resp.choices[0].message.content or "").strip()[:200]

    return {"title": title, "markdown": content, "summary": summary}
