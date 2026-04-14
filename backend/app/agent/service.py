"""Agent 核心服务：会话管理 + 流式聊天编排"""
import asyncio
import json
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, AsyncGenerator, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.models import ChatSession, ChatMessage
from app.agent.llm import client
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, TOOL_NAME_MAP
from app.agent.executor import execute_tool

settings = get_settings()

CALENDAR_TOOL_NAME = "get_upcoming_launches"
CALENDAR_KEYWORDS = (
    "日历", "发行日历", "发售日程", "发售时间", "上新时间", "发售计划", "什么时候发售",
    "哪天发售", "即将发行", "近期发行", "最近发行", "calendar", "schedule", "upcoming",
)
MARKET_KEYWORDS = (
    "行情", "市值", "成交额", "成交量", "地板价", "最低价", "均价", "市场表现", "市场价",
)
TREND_KEYWORDS = (
    "走势", "趋势", "曲线", "k线", "价格变化", "涨跌", "趋势图", "涨了", "跌了",
)
HOT_KEYWORDS = (
    "热榜", "热门", "排行", "排名", "top", "榜单",
)
IP_KEYWORDS = (
    "ip", "创作者", "发行方", "系列", "旗下", "作者",
)
IP_RANKING_KEYWORDS = (
    "ip排行", "ip排名", "创作者排行", "创作者排名", "ip热度", "ip榜",
)
CATEGORY_KEYWORDS = (
    "鲸探50", "禁出195", "新品", "分类", "分类排行", "行情分类", "秒转",
)
SECTOR_KEYWORDS = (
    "板块", "字画", "文物", "非遗", "plane", "sector", "平台",
)
STATS_KEYWORDS = (
    "概览", "统计", "总数", "数据库", "数据量", "平台数据",
)
DETAIL_KEYWORDS = (
    "详情", "介绍", "信息", "什么", "怎么样", "值得", "资料",
)
PRONOUN_KEYWORDS = (
    "它", "这个", "这个藏品", "该藏品", "这个ip", "该ip", "ta", "其",
)
MARKET_OVERVIEW_KEYWORDS = (
    "市场概况", "市场概览", "今日市场", "市场总览", "大盘", "全市场",
    "市场整体", "整体行情", "市场怎么样", "市场行情",
)
CENSUS_KEYWORDS = (
    "涨跌分布", "涨跌统计", "涨跌情况", "成交统计", "成交详细",
    "涨了多少", "跌了多少", "多少涨多少跌", "普查",
)
LISTING_KEYWORDS = (
    "挂单", "在售", "挂售", "最低价挂单", "买入", "出售", "挂牌",
    "二级市场", "多少钱", "目前价格", "现在卖",
)
JINGTAN_KEYWORDS = (
    "sku", "百科", "鲸探官方", "官方数据", "发行信息", "收藏数",
    "作者是谁", "谁创作", "鲸探sku", "鲸探",
)
HISTORY_KEYWORDS = (
    "历史", "昨天", "前天", "上周", "上个月", "某天", "历史对比",
    "历史数据", "往期", "过去", "之前的", "回顾",
)
LAUNCH_DETAIL_KEYWORDS = (
    "优先购", "优先购条件", "发行详情", "发售详情", "购买条件", "怎么买", "资格",
)
RESOLVE_TOOL_NAME = "resolve_entities"
BASE_ENTITY_TOOLS = {
    RESOLVE_TOOL_NAME,
    "search_archives",
    "search_ips",
    "online_search_archives",
    "online_search_ips",
    "get_archive_detail",
    "get_ip_detail",
}
SELECTION_REPLY_PATTERN = re.compile(r"^\s*(?:选|选择|就选|我要|看|查)?\s*(?:第\s*)?(\d{1,2})\s*(?:个|项|条)?\s*$")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lower_text = text.lower()
    return any(k in text or k in lower_text for k in keywords)


def _normalize_user_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip().lower()


def _is_selection_reply(text: str) -> bool:
    return bool(SELECTION_REPLY_PATTERN.match(text or ""))


def _is_calendar_intent(user_text: str) -> bool:
    return _contains_any(user_text, CALENDAR_KEYWORDS)


_GENERIC_TEXTS = {"你好", "hi", "hello", "在吗", "帮我查", "帮我看看", "查一下", "问一下"}

_INTENT_LABEL_MAP = {
    "calendar": "发行日历",
    "market": "行情查询",
    "trend": "走势分析",
    "hot": "热榜",
    "ip_ranking": "IP排行",
    "category": "分类排行",
    "sector": "板块",
    "stats": "数据概览",
    "detail": "详情查询",
    "market_overview": "市场概况",
    "census": "成交统计",
    "listing": "挂单查询",
    "jingtan": "鲸探百科",
    "history": "历史对比",
    "launch_detail": "发行详情",
}


def _generate_session_title(user_text: str, intent: dict[str, bool] | None = None) -> str | None:
    """生成有意义的会话标题。返回 None 表示暂不设置（等后续轮次补充）"""
    text = user_text.strip()
    if not text or _normalize_user_text(text) in _GENERIC_TEXTS or len(text) <= 3:
        return None

    # 从意图标签提取前缀
    prefix = ""
    if intent:
        for key, label in _INTENT_LABEL_MAP.items():
            if intent.get(key):
                prefix = label
                break

    # 清理用户文本，截取核心部分
    core = re.sub(r"[？?!！。，,\s]+$", "", text)[:30]
    if prefix and prefix not in core:
        return f"{prefix}·{core}"
    return core


def _classify_intent(user_text: str) -> dict[str, bool]:
    text = user_text.strip()
    return {
        "calendar": _contains_any(text, CALENDAR_KEYWORDS),
        "market": _contains_any(text, MARKET_KEYWORDS),
        "trend": _contains_any(text, TREND_KEYWORDS),
        "hot": _contains_any(text, HOT_KEYWORDS),
        "ip": _contains_any(text, IP_KEYWORDS),
        "ip_ranking": _contains_any(text, IP_RANKING_KEYWORDS),
        "category": _contains_any(text, CATEGORY_KEYWORDS),
        "sector": _contains_any(text, SECTOR_KEYWORDS),
        "stats": _contains_any(text, STATS_KEYWORDS),
        "detail": _contains_any(text, DETAIL_KEYWORDS),
        "pronoun_followup": _contains_any(text, PRONOUN_KEYWORDS),
        "market_overview": _contains_any(text, MARKET_OVERVIEW_KEYWORDS),
        "census": _contains_any(text, CENSUS_KEYWORDS),
        "listing": _contains_any(text, LISTING_KEYWORDS),
        "jingtan": _contains_any(text, JINGTAN_KEYWORDS),
        "history": _contains_any(text, HISTORY_KEYWORDS),
        "launch_detail": _contains_any(text, LAUNCH_DETAIL_KEYWORDS),
    }


def _select_tools(user_text: str) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    intent = _classify_intent(user_text)
    selected_names: set[str] = set()

    if intent["calendar"]:
        selected_names.add(CALENDAR_TOOL_NAME)
    if intent["launch_detail"]:
        selected_names.update({CALENDAR_TOOL_NAME, "get_launch_detail"})
    if intent["stats"]:
        selected_names.add("get_db_stats")
    if intent["market_overview"]:
        selected_names.add("get_market_overview")
    if intent["category"]:
        selected_names.update({"get_market_categories", "get_category_archives"})
        if intent["census"]:
            selected_names.add("get_top_census")
    if intent["sector"]:
        selected_names.update({"get_sector_stats", "get_plane_list", "get_sector_archives"})
        if intent["census"]:
            selected_names.add("get_plane_census")
    if intent["census"] and not intent["sector"] and not intent["category"]:
        selected_names.update({"get_plane_census", "get_top_census", "get_plane_list", "get_market_categories"})
    if intent["ip_ranking"]:
        selected_names.add("get_ip_ranking")
    elif intent["hot"]:
        selected_names.add("get_hot_archives")
    if intent["market"]:
        selected_names.add("get_archive_market")
    if intent["trend"]:
        selected_names.add("get_archive_price_trend")
    if intent["listing"]:
        selected_names.add("get_archive_goods_listing")
    if intent["jingtan"] or intent["detail"]:
        selected_names.update({"search_jingtan_sku", "get_jingtan_sku_detail"})
    if intent["history"]:
        selected_names.add("get_market_history")

    needs_entity_tools = any(
        [
            intent["market"],
            intent["trend"],
            intent["detail"],
            intent["ip"],
            intent["pronoun_followup"],
            intent["listing"],
        ]
    ) or not selected_names
    if needs_entity_tools:
        selected_names.update(BASE_ENTITY_TOOLS)

    selected_tools = [t for t in TOOLS if t["function"]["name"] in selected_names]
    return selected_tools, intent


# ── 会话 CRUD ────────────────────────────────────────

async def create_session(db: AsyncSession, user_id: int, title: str = "新对话") -> ChatSession:
    session = ChatSession(user_id=user_id, title=title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(db: AsyncSession, user_id: int) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def delete_session(db: AsyncSession, session_id: int, user_id: int) -> bool:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return False
    await db.delete(session)
    await db.commit()
    return True


async def get_messages(db: AsyncSession, session_id: int, user_id: int) -> Optional[list[ChatMessage]]:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        return None
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(msg_result.scalars().all())


def _build_candidate(entity_type: str, entity_id: Any, name: str | None, source: str | None, match_type: str | None = None) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "id": entity_id,
        "name": name,
        "source": source,
        "match_type": match_type,
    }


def _append_entity(target: list[dict[str, Any]], entity: dict[str, Any], key: str) -> None:
    entity_key = entity.get(key)
    if entity_key is None:
        return
    if any(existing.get(key) == entity_key for existing in target):
        return
    target.append(entity)


def _extract_recent_context(recent: list[ChatMessage]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """单次遍历历史消息，同时提取最近实体和候选列表"""
    entities: dict[str, list[dict[str, Any]]] = {"archives": [], "ips": []}
    candidates: list[dict[str, Any]] = []
    candidates_found = False

    for message in reversed(recent):
        if message.role != "tool" or not message.content:
            continue
        try:
            data = json.loads(message.content)
        except json.JSONDecodeError:
            continue

        # ── 提取实体 ──
        if message.name in {"get_archive_detail"}:
            _append_entity(entities["archives"], {
                "archive_id": data.get("archive_id"),
                "name": data.get("name"),
                "ip": data.get("ip"),
            }, "archive_id")
        elif message.name in {"search_archives", "online_search_archives", "get_hot_archives", "get_category_archives", "get_sector_archives", "resolve_entities"}:
            items = data.get("items") or data.get("archives") or []
            for item in items[:3]:
                archive_id = item.get("archive_id") or item.get("archiveId")
                _append_entity(entities["archives"], {
                    "archive_id": archive_id,
                    "name": item.get("name"),
                    "ip": item.get("ip"),
                }, "archive_id")

        if message.name in {"get_ip_detail"}:
            _append_entity(entities["ips"], {
                "id": data.get("id"),
                "name": data.get("name"),
            }, "id")
        elif message.name in {"search_ips", "online_search_ips", "get_ip_ranking", "resolve_entities"}:
            items = data.get("items") or data.get("ips") or []
            for item in items[:3]:
                ip_id = item.get("id") or item.get("source_uid")
                if ip_id is None:
                    continue
                _append_entity(entities["ips"], {
                    "id": ip_id,
                    "name": item.get("name"),
                }, "id")

        # ── 提取候选（只取最近一轮的） ──
        if not candidates_found:
            if message.name == "resolve_entities":
                recommendations = data.get("recommendations") or []
                if recommendations:
                    candidates = recommendations[:5]
                    candidates_found = True

            if not candidates_found and message.name in {"search_archives", "online_search_archives"}:
                items = data.get("items") or []
                found = [
                    _build_candidate(
                        "online_archive" if message.name == "online_search_archives" else "archive",
                        item.get("archive_id"),
                        item.get("name"),
                        item.get("source"),
                        item.get("match_type"),
                    )
                    for item in items[:5]
                    if item.get("archive_id") and item.get("name")
                ]
                if found:
                    candidates = found
                    candidates_found = True

            if not candidates_found and message.name in {"search_ips", "online_search_ips"}:
                items = data.get("items") or []
                found = [
                    _build_candidate(
                        "online_ip" if message.name == "online_search_ips" else "ip",
                        item.get("id") or item.get("source_uid"),
                        item.get("name"),
                        item.get("source"),
                        item.get("match_type"),
                    )
                    for item in items[:5]
                    if (item.get("id") or item.get("source_uid")) is not None and item.get("name")
                ]
                if found:
                    candidates = found
                    candidates_found = True

        # 两个目标都完成时提前退出
        entities_full = len(entities["archives"]) >= 3 and len(entities["ips"]) >= 3
        if entities_full and candidates_found:
            break

    return entities, candidates


def _find_previous_user_text(recent: list[ChatMessage]) -> str | None:
    if not recent:
        return None
    for message in reversed(recent[:-1]):
        if message.role == "user" and message.content and not _is_selection_reply(message.content):
            return message.content
    return None


def _resolve_selected_candidate(user_text: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not user_text or not candidates:
        return None

    match = SELECTION_REPLY_PATTERN.match(user_text)
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(candidates):
            return candidates[index]

    normalized_text = _normalize_user_text(user_text)
    for candidate in candidates:
        candidate_name = _normalize_user_text(str(candidate.get("name") or ""))
        if candidate_name and normalized_text == candidate_name:
            return candidate
    return None


def _format_selected_candidate(candidate: dict[str, Any]) -> str:
    entity_type = candidate.get("entity_type")
    name = candidate.get("name") or "未知对象"
    if entity_type in {"archive", "online_archive"}:
        return f"已确认藏品：{name}；内部 archive_id={candidate.get('id')}。该内部ID仅供工具调用，最终回复禁止展示。"
    if entity_type in {"ip", "online_ip"}:
        label = "ip_id" if entity_type == "ip" else "source_uid"
        return f"已确认IP：{name}；内部 {label}={candidate.get('id')}。该内部ID仅供工具调用，最终回复禁止展示。"
    return f"已确认对象：{name}。"


def _format_recent_entities(recent_entities: dict[str, list[dict[str, Any]]]) -> str:
    parts: list[str] = []
    if recent_entities["archives"]:
        archive_text = "；".join(
            f"{item['name']}"
            for item in recent_entities["archives"][:3]
            if item.get("archive_id") and item.get("name")
        )
        if archive_text:
            parts.append(f"最近提到的藏品：{archive_text}")
    if recent_entities["ips"]:
        ip_text = "；".join(
            f"{item['name']}"
            for item in recent_entities["ips"][:3]
            if item.get("id") is not None and item.get("name")
        )
        if ip_text:
            parts.append(f"最近提到的IP：{ip_text}")
    return "\n".join(parts)


def _build_runtime_guidance(
    user_text: str,
    intent: dict[str, bool],
    recent_entities: dict[str, list[dict[str, Any]]],
    selected_tools: list[dict[str, Any]],
    selected_candidate: dict[str, Any] | None = None,
    effective_query: str | None = None,
) -> str:
    selected_tool_names = ", ".join(t["function"]["name"] for t in selected_tools)
    rules: list[str] = [
        "只用与当前问题相关的工具，不为求全而扩展。",
        "调用工具时直接发起，不输出过渡文字。",
        "藏品/IP名查详情/行情/走势 → 先 resolve_entities。",
        "多候选无best_match → 用编号列表让用户确认（只显示名称+平台）。",
        "DB空 → 在线查询推荐候选。",
        "工具返回 public_items/public_recommendations → 优先使用。",
        "最终回复禁止暴露内部ID、工具名、英文字段。",
    ]
    if intent["calendar"]:
        rules.append("发行/发售问题 → 用发行日历工具，不扩展行情。")
    if intent["hot"] or intent["ip_ranking"] or intent["category"] or intent["sector"]:
        rules.append("排行/列表类 → 先给列表，不擅自展开单个详情。")
    if intent.get("market_overview"):
        rules.append("市场概况 → get_market_overview，无需实体确认。")
    if intent.get("census"):
        rules.append("涨跌分布 → get_plane_census / get_top_census。")
    if intent.get("jingtan"):
        rules.append("鲸探百科 → search_jingtan_sku / get_jingtan_sku_detail。")
    if intent.get("history"):
        rules.append("历史对比 → get_market_history。")
    if intent.get("listing"):
        rules.append("挂单查询 → 确认实体后 get_archive_goods_listing。")
    if intent.get("launch_detail"):
        rules.append("发行详情/优先购 → get_launch_detail。")

    recent_context_text = _format_recent_entities(recent_entities)
    guidance_lines = [
        f"用户: {user_text}",
        f"允许工具: {selected_tool_names}",
        "规则: " + " | ".join(rules),
    ]
    if recent_context_text:
        guidance_lines.append(recent_context_text)
    if effective_query and effective_query != user_text:
        guidance_lines.append(f"原始需求: {effective_query}")
    if selected_candidate:
        guidance_lines.append(_format_selected_candidate(selected_candidate))

    return "\n".join(guidance_lines)


def _inject_runtime_guidance(messages: list[dict], guidance: str) -> list[dict]:
    runtime_message = {"role": "system", "content": guidance}
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            return messages[:index] + [runtime_message] + messages[index:]
    return [*messages, runtime_message]


# ── 历史构建 ─────────────────────────────────────────

async def _load_history(db: AsyncSession, session_id: int) -> tuple[list[dict], dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    started = perf_counter()
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(settings.AGENT_MAX_HISTORY)
    )
    recent = list(reversed(result.scalars().all()))
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    truncation_events: list[dict[str, Any]] = []

    for m in recent:
        msg_dict: dict = {"role": m.role}
        if m.content is not None:
            content = m.content
            if m.role == "tool" and len(content) > 800:
                trunc_start = perf_counter()
                original_length = len(content)
                content = content[:800] + "\n...(历史数据已省略)"
                truncation_events.append({
                    "role": m.role,
                    "tool_name": m.name,
                    "original_length": original_length,
                    "truncated_length": len(content),
                    "elapsed_ms": round((perf_counter() - trunc_start) * 1000, 3),
                })
            msg_dict["content"] = content
        if m.tool_calls:
            try:
                msg_dict["tool_calls"] = json.loads(m.tool_calls)
            except json.JSONDecodeError:
                pass
        if m.tool_call_id:
            msg_dict["tool_call_id"] = m.tool_call_id
        if m.name:
            msg_dict["name"] = m.name
        messages.append(msg_dict)

    profiling = {
        "history_load_ms": round((perf_counter() - started) * 1000, 3),
        "history_message_count": len(recent),
        "truncation_count": len(truncation_events),
        "truncation_events": truncation_events,
    }
    recent_entities, recent_candidates = _extract_recent_context(recent)
    conversation_context = {
        "recent_candidates": recent_candidates,
        "previous_user_text": _find_previous_user_text(recent),
    }
    return messages, profiling, recent_entities, conversation_context


# ── 推荐问题 ─────────────────────────────────────────

def _generate_suggestions(tools_used: list[str]) -> list[str]:
    """根据本轮使用的工具，生成相关后续问题建议"""
    pool: list[str] = []
    tool_set = set(tools_used)

    if "get_hot_archives" in tool_set:
        pool.extend(["查看近7天成交热榜", "查看板块统计数据", "今日市场概况"])
    if "search_archives" in tool_set or "get_archive_detail" in tool_set:
        pool.extend(["查看该藏品实时行情", "查看价格走势图", "查看挂单情况"])
    if "get_archive_market" in tool_set:
        pool.extend(["查看近7天行情变化", "查看该藏品挂单列表", "对比其他热门藏品"])
    if "get_archive_price_trend" in tool_set:
        pool.extend(["查看近30天价格走势", "查看今日成交热榜"])
    if "get_ip_ranking" in tool_set:
        pool.extend(["查看某个IP的详细信息", "查看板块统计"])
    if "search_ips" in tool_set or "get_ip_detail" in tool_set:
        pool.extend(["查看IP旗下藏品行情", "查看IP热度排行榜"])
    if "get_sector_stats" in tool_set:
        pool.extend(["查看某板块涨跌分布", "查看板块下藏品交易", "查看IP排行榜"])
    if "get_upcoming_launches" in tool_set:
        pool.extend(["查看某个发行的详情和优先购条件", "查看平台数据概览"])
    if "get_db_stats" in tool_set:
        pool.extend(["查看今日市场概况", "查看成交热榜", "查看近期发行日历"])
    if "get_market_categories" in tool_set or "get_category_archives" in tool_set:
        pool.extend(["查看鲸探50涨跌分布", "查看其他行情分类"])
    if "get_plane_list" in tool_set or "get_sector_archives" in tool_set:
        pool.extend(["查看板块涨跌详细统计", "查看板块统计概览"])
    if "get_market_overview" in tool_set:
        pool.extend(["查看板块统计详情", "查看成交热榜", "查看IP排行"])
    if "get_plane_census" in tool_set or "get_top_census" in tool_set:
        pool.extend(["查看板块下藏品交易排行", "查看其他板块涨跌分布"])
    if "get_archive_goods_listing" in tool_set:
        pool.extend(["查看藏品行情走势", "查看藏品市场数据"])
    if "search_jingtan_sku" in tool_set or "get_jingtan_sku_detail" in tool_set:
        pool.extend(["搜索其他鲸探藏品百科", "查看该藏品的市场行情"])
    if "get_market_history" in tool_set:
        pool.extend(["对比其他日期的数据", "查看今日实时数据"])
    if "get_launch_detail" in tool_set:
        pool.extend(["查看近期其他发行", "查看该藏品市场行情"])

    if not pool:
        pool = ["今天市场概况怎么样", "今天成交热榜前10是哪些", "查看板块统计数据", "近期有哪些新品发行"]

    seen: set[str] = set()
    unique: list[str] = []
    for s in pool:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:3]


# ── SSE 格式化 ────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 流式聊天核心 ─────────────────────────────────────

async def stream_chat(
    db: AsyncSession,
    session_id: int,
    user_id: int,
    content: str,
) -> AsyncGenerator[str, None]:
    """
    SSE 流式聊天。

    优化点:
    1. 历史消息只从 DB 加载一次，后续在内存追加
    2. 当 LLM 无 tool_calls 时直接输出答案，省去额外一次流式 LLM 调用
    3. 每轮 tool 执行后批量提交 DB，减少 IO
    4. 截断过长的历史 tool 结果，节省 token
    5. 回答结束后推送关联问题建议

    事件类型:
    - tool_call: {"type":"tool_call", "name":"xxx", "label":"搜索藏品"}
    - content:   {"type":"content", "text":"..."}
    - done:      {"type":"done", "suggestions":["...", ...]}
    - error:     {"type":"error", "message":"..."}
    """
    request_started = perf_counter()
    profiling: dict[str, Any] = {"stages": {}, "tool_calls": [], "truncations": []}
    stage_started = perf_counter()
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    profiling["stages"]["verify_session_ms"] = round((perf_counter() - stage_started) * 1000, 3)
    session = result.scalar_one_or_none()
    if not session:
        yield _sse({"type": "error", "message": "会话不存在"})
        return

    stage_started = perf_counter()
    db.add(ChatMessage(session_id=session_id, role="user", content=content))
    needs_title = session.title == "新对话"
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    profiling["stages"]["save_user_message_ms"] = round((perf_counter() - stage_started) * 1000, 3)

    try:
        messages, history_profiling, recent_entities, conversation_context = await _load_history(db, session_id)
        selected_candidate = _resolve_selected_candidate(content, conversation_context.get("recent_candidates", []))
        effective_query = conversation_context.get("previous_user_text") if selected_candidate else content
        effective_query = effective_query or content
        selected_tools, intent_profile = _select_tools(effective_query)

        # 延迟生成会话标题：结合意图信息生成更有意义的标题
        if needs_title:
            title = _generate_session_title(content, intent_profile)
            if title:
                session.title = title
                await db.commit()

        profiling["selected_tool_count"] = len(selected_tools)
        profiling["selected_tools"] = [tool["function"]["name"] for tool in selected_tools]
        profiling["intent_profile"] = intent_profile
        profiling["calendar_intent"] = intent_profile["calendar"]
        profiling["effective_query"] = effective_query
        if selected_candidate:
            profiling["selected_candidate"] = {
                "name": selected_candidate.get("name"),
                "entity_type": selected_candidate.get("entity_type"),
            }

        round_limit = settings.AGENT_MAX_TOOL_ROUNDS
        if not profiling["calendar_intent"]:
            round_limit = min(round_limit, 6)
        profiling["stages"]["load_history_ms"] = history_profiling["history_load_ms"]
        profiling["history_message_count"] = history_profiling["history_message_count"]
        profiling["truncations"] = history_profiling["truncation_events"]
        profiling["recent_entities"] = recent_entities
        runtime_guidance = _build_runtime_guidance(
            content,
            intent_profile,
            recent_entities,
            selected_tools,
            selected_candidate=selected_candidate,
            effective_query=effective_query,
        )
        messages = _inject_runtime_guidance(messages, runtime_guidance)
        tools_used: list[str] = []
        # 中间轮次用更少 max_tokens，加速 tool_call 生成
        intermediate_max_tokens = min(settings.LLM_MAX_TOKENS, 2048)

        for _round in range(round_limit):
            llm_started = perf_counter()
            is_last_chance = _round == round_limit - 1
            cur_max_tokens = settings.LLM_MAX_TOKENS if is_last_chance else intermediate_max_tokens

            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=selected_tools if not is_last_chance else None,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=cur_max_tokens,
                stream=True,
            )

            # ── 早期检测模式：根据首个 delta 判断是流式文本还是工具调用 ──
            # 避免全部缓冲后再回放，实现真正的逐 token 流式输出
            mode: str = "detecting"  # detecting → streaming | buffering
            streamed_content = ""
            content_chunks: list[str] = []
            streamed_tool_calls: dict[int, dict] = {}

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                if mode == "detecting":
                    if delta.tool_calls:
                        mode = "buffering"
                    elif delta.content:
                        mode = "streaming"

                if delta.content:
                    streamed_content += delta.content
                    if mode == "streaming":
                        # 真流式：边收到边推给用户
                        yield _sse({"type": "content", "text": delta.content})
                    else:
                        content_chunks.append(delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in streamed_tool_calls:
                            streamed_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            streamed_tool_calls[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                streamed_tool_calls[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                streamed_tool_calls[idx]["arguments"] += tc_delta.function.arguments

            profiling["stages"][f"llm_round_{_round + 1}_ms"] = round((perf_counter() - llm_started) * 1000, 3)

            # 无 tool_calls → 纯文本回答（最终答案）
            if not streamed_tool_calls:
                if streamed_content:
                    # buffering 模式下的文本需要补发（detecting 阶段的文本已在 streaming 模式下发送）
                    if mode == "buffering":
                        for text_chunk in content_chunks:
                            yield _sse({"type": "content", "text": text_chunk})
                    save_started = perf_counter()
                    db.add(ChatMessage(
                        session_id=session_id, role="assistant", content=streamed_content,
                    ))
                    await db.commit()
                    profiling["stages"]["save_assistant_message_ms"] = round((perf_counter() - save_started) * 1000, 3)
                profiling["stages"]["total_ms"] = round((perf_counter() - request_started) * 1000, 3)
                yield _sse({
                    "type": "done",
                    "suggestions": _generate_suggestions(tools_used),
                    "profiling": profiling,
                })
                return

            # ── 有 tool_calls → 执行工具 ──
            tc_list = [
                {
                    "id": streamed_tool_calls[idx]["id"],
                    "type": "function",
                    "function": {
                        "name": streamed_tool_calls[idx]["name"],
                        "arguments": streamed_tool_calls[idx]["arguments"],
                    },
                }
                for idx in sorted(streamed_tool_calls.keys())
            ]

            # 内存追加 assistant(tool_calls)，丢弃思考文本避免下轮重复
            assistant_msg: dict = {"role": "assistant", "tool_calls": tc_list}
            messages.append(assistant_msg)

            # DB 追加（不立即提交），不保存思考文本
            db.add(ChatMessage(
                session_id=session_id,
                role="assistant",
                content=None,
                tool_calls=json.dumps(tc_list),
            ))

            # 先发出所有 tool_call 事件，再并行执行
            parsed_calls: list[tuple[str, str, dict]] = []  # (tool_call_id, tool_name, args)
            for tc_item in tc_list:
                tool_name = tc_item["function"]["name"]
                tool_call_id = tc_item["id"]
                label = TOOL_NAME_MAP.get(tool_name, tool_name)
                tools_used.append(tool_name)
                yield _sse({"type": "tool_call", "name": tool_name, "label": label})
                try:
                    args = json.loads(tc_item["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {"_raw_arguments": tc_item["function"]["arguments"]}
                parsed_calls.append((tool_call_id, tool_name, args))

            # 并行执行所有工具
            tool_started = perf_counter()
            tool_tasks = [
                execute_tool(tool_name, args, db)
                for (_, tool_name, args) in parsed_calls
            ]
            tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)
            total_tool_ms = round((perf_counter() - tool_started) * 1000, 3)

            for (tool_call_id, tool_name, _args), result in zip(parsed_calls, tool_results):
                if isinstance(result, Exception):
                    logger.exception(f"Tool {tool_name} 并行执行失败")
                    tool_result = json.dumps({"error": f"工具执行失败: {str(result)}"}, ensure_ascii=False)
                else:
                    tool_result = result
                profiling["tool_calls"].append({
                    "name": tool_name,
                    "elapsed_ms": total_tool_ms,
                    "result_length": len(tool_result),
                })
                # 给 LLM 的上下文截断，降低下一轮 token 消耗
                llm_tool_result = tool_result
                if len(llm_tool_result) > 3000:
                    llm_tool_result = llm_tool_result[:3000] + "\n...(数据已截断，核心内容在上方)"
                messages.append({
                    "role": "tool",
                    "content": llm_tool_result,
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                })
                # DB 保存完整结果
                db.add(ChatMessage(
                    session_id=session_id,
                    role="tool",
                    content=tool_result,
                    tool_call_id=tool_call_id,
                    name=tool_name,
                ))

            commit_started = perf_counter()
            await db.commit()
            profiling["stages"][f"commit_round_{_round + 1}_ms"] = round((perf_counter() - commit_started) * 1000, 3)
            logger.debug(f"Tool round {_round + 1} done ({len(parsed_calls)} tools parallel, {total_tool_ms}ms)")

        # 达到轮次上限后的最终流式回答
        final_started = perf_counter()
        final_stream = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            stream=True,
        )
        full_content = ""
        async for chunk in final_stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_content += delta.content
                yield _sse({"type": "content", "text": delta.content})
        profiling["stages"]["final_stream_ms"] = round((perf_counter() - final_started) * 1000, 3)

        if full_content:
            save_started = perf_counter()
            db.add(ChatMessage(
                session_id=session_id, role="assistant", content=full_content,
            ))
            await db.commit()
            profiling["stages"]["save_assistant_message_ms"] = round((perf_counter() - save_started) * 1000, 3)

        profiling["stages"]["total_ms"] = round((perf_counter() - request_started) * 1000, 3)
        yield _sse({
            "type": "done",
            "suggestions": _generate_suggestions(tools_used),
            "profiling": profiling,
        })

    except Exception as e:
        logger.exception("Agent 聊天失败")
        yield _sse({"type": "error", "message": str(e)})

