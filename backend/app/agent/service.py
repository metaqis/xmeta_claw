"""Agent 核心服务：会话管理 + 流式聊天编排"""
import json
from datetime import datetime
from typing import AsyncGenerator, Optional

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


# ── 历史构建 ─────────────────────────────────────────

async def _load_history(db: AsyncSession, session_id: int) -> list[dict]:
    """从 DB 加载历史消息，截断到 MAX_HISTORY，返回 OpenAI 格式列表"""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    all_msgs = result.scalars().all()

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    recent = all_msgs[-settings.AGENT_MAX_HISTORY:] if len(all_msgs) > settings.AGENT_MAX_HISTORY else all_msgs

    for m in recent:
        msg_dict: dict = {"role": m.role}
        if m.content is not None:
            content = m.content
            # 截断过长的历史工具返回，节省 token
            if m.role == "tool" and len(content) > 1500:
                content = content[:1500] + "\n...(历史数据已省略)"
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

    return messages


# ── 推荐问题 ─────────────────────────────────────────

def _generate_suggestions(tools_used: list[str]) -> list[str]:
    """根据本轮使用的工具，生成相关后续问题建议"""
    pool: list[str] = []
    tool_set = set(tools_used)

    if "get_hot_archives" in tool_set:
        pool.extend(["查看近7天成交热榜", "查看板块统计数据"])
    if "search_archives" in tool_set or "get_archive_detail" in tool_set:
        pool.extend(["查看该藏品实时行情", "查看价格走势图"])
    if "get_archive_market" in tool_set:
        pool.extend(["查看近7天行情变化", "对比其他热门藏品"])
    if "get_archive_price_trend" in tool_set:
        pool.extend(["查看近30天价格走势", "查看今日成交热榜"])
    if "get_ip_ranking" in tool_set:
        pool.extend(["查看某个IP的详细信息", "查看板块统计"])
    if "search_ips" in tool_set or "get_ip_detail" in tool_set:
        pool.extend(["查看IP旗下藏品行情", "查看IP热度排行榜"])
    if "get_sector_stats" in tool_set:
        pool.extend(["查看某板块下的藏品交易", "查看IP排行榜"])
    if "get_upcoming_launches" in tool_set:
        pool.extend(["搜索即将发行的藏品详情", "查看平台数据概览"])
    if "get_db_stats" in tool_set:
        pool.extend(["查看今日成交热榜", "查看近期发行日历"])
    if "get_market_categories" in tool_set or "get_category_archives" in tool_set:
        pool.extend(["查看鲸探50排行", "查看其他行情分类"])
    if "get_plane_list" in tool_set or "get_sector_archives" in tool_set:
        pool.extend(["查看其他板块的藏品交易", "查看板块统计概览"])

    if not pool:
        pool = ["今天成交热榜前10是哪些", "查看板块统计数据", "近期有哪些新品发行"]

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
    # ── 验证会话 ──
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        yield _sse({"type": "error", "message": "会话不存在"})
        return

    # ── 保存用户消息 + 更新会话 ──
    db.add(ChatMessage(session_id=session_id, role="user", content=content))
    if session.title == "新对话":
        session.title = content[:50]
    session.updated_at = datetime.utcnow()
    await db.commit()

    try:
        # 从 DB 加载历史（整个请求只查一次），后续在内存追加
        messages = await _load_history(db, session_id)
        tools_used: list[str] = []

        # ── Tool 循环（非流式） ──
        for _round in range(settings.AGENT_MAX_TOOL_ROUNDS):
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=TOOLS,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
            choice = response.choices[0]

            if not choice.message.tool_calls:
                # 无工具调用 → 直接使用此回答（省去额外一次 LLM 调用）
                final_text = choice.message.content or ""
                for i in range(0, len(final_text), 20):
                    yield _sse({"type": "content", "text": final_text[i:i + 20]})
                if final_text:
                    db.add(ChatMessage(
                        session_id=session_id, role="assistant", content=final_text,
                    ))
                    await db.commit()
                yield _sse({"type": "done", "suggestions": _generate_suggestions(tools_used)})
                return

            # ── 有 tool_calls → 执行工具 ──
            tc_list = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

            # 内存追加 assistant(tool_calls)
            assistant_msg: dict = {"role": "assistant", "tool_calls": tc_list}
            if choice.message.content:
                assistant_msg["content"] = choice.message.content
            messages.append(assistant_msg)

            # DB 追加（不立即提交）
            db.add(ChatMessage(
                session_id=session_id,
                role="assistant",
                content=choice.message.content,
                tool_calls=json.dumps(tc_list),
            ))

            # 逐个执行工具（共享 db session，需串行）
            for tc in choice.message.tool_calls:
                tool_name = tc.function.name
                label = TOOL_NAME_MAP.get(tool_name, tool_name)
                tools_used.append(tool_name)
                yield _sse({"type": "tool_call", "name": tool_name, "label": label})

                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_result = await execute_tool(tool_name, args, db)

                messages.append({
                    "role": "tool",
                    "content": tool_result,
                    "tool_call_id": tc.id,
                    "name": tool_name,
                })
                db.add(ChatMessage(
                    session_id=session_id,
                    role="tool",
                    content=tool_result,
                    tool_call_id=tc.id,
                    name=tool_name,
                ))

            # 批量提交本轮消息
            await db.commit()
            logger.debug(f"Tool round {_round + 1} done")

        # ── 达到最大轮次 → 流式最终回答 ──
        stream = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            stream=True,
        )
        full_content = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_content += delta.content
                yield _sse({"type": "content", "text": delta.content})

        if full_content:
            db.add(ChatMessage(
                session_id=session_id, role="assistant", content=full_content,
            ))
            await db.commit()

        yield _sse({"type": "done", "suggestions": _generate_suggestions(tools_used)})

    except Exception as e:
        logger.exception("Agent 聊天失败")
        yield _sse({"type": "error", "message": str(e)})
