"""Agent AI 助手 API"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.db import get_db, async_session
from app.database.models import User
from app.agent.service import (
    create_session,
    list_sessions,
    delete_session,
    get_messages,
    stream_chat,
)

router = APIRouter(prefix="/agent", tags=["AI助手"])


# ── 请求/响应模型 ──────────────────────────────────

class CreateSessionRequest(BaseModel):
    title: str = "新对话"


class ChatRequest(BaseModel):
    session_id: int
    content: str


class SessionResponse(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str | None = None
    tool_calls: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    created_at: str

    class Config:
        from_attributes = True


# ── 会话管理 ───────────────────────────────────────

@router.post("/sessions", response_model=SessionResponse)
async def api_create_session(
    req: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await create_session(db, user.id, req.title)
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def api_list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await list_sessions(db, user.id)
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def api_delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_session(db, session_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"message": "已删除"}


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def api_get_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    msgs = await get_messages(db, session_id, user.id)
    if msgs is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            tool_calls=m.tool_calls,
            tool_call_id=m.tool_call_id,
            name=m.name,
            created_at=m.created_at.isoformat(),
        )
        for m in msgs
    ]


# ── 流式聊天 ───────────────────────────────────────

@router.post("/chat")
async def api_chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
):
    """
    SSE 流式聊天。
    注意: 使用独立 async_session 而非 Depends(get_db)，
    因为 StreamingResponse 的 generator 在依赖生命周期结束后才执行。
    """
    async def event_generator():
        async with async_session() as db:
            async for event in stream_chat(db, req.session_id, user.id, req.content):
                yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
