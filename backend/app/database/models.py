from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, BigInteger, Index
)
from sqlalchemy.orm import relationship
from app.database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")  # admin / viewer
    created_at = Column(DateTime, default=datetime.utcnow)


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

    ips = relationship("IP", back_populates="platform")
    launch_calendars = relationship("LaunchCalendar", back_populates="platform")
    archives = relationship("Archive", back_populates="platform")


class IP(Base):
    __tablename__ = "ips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_uid = Column(Integer, unique=True, index=True)
    from_type = Column(Integer, default=1)
    ip_name = Column(String(200), nullable=False)
    ip_avatar = Column(String(500))
    description = Column(Text)
    fans_count = Column(Integer)
    platform_id = Column(Integer, ForeignKey("platforms.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    platform = relationship("Platform", back_populates="ips")
    launch_calendars = relationship("LaunchCalendar", back_populates="ip")
    archives = relationship("Archive", back_populates="ip")


class LaunchCalendar(Base):
    __tablename__ = "launch_calendar"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(300), nullable=False)
    sell_time = Column(DateTime, index=True)
    price = Column(Float)
    count = Column(Integer)
    platform_id = Column(Integer, ForeignKey("platforms.id"), index=True)
    ip_id = Column(Integer, ForeignKey("ips.id"), index=True)
    img = Column(String(500))
    priority_purchase_num = Column(Integer, default=0)
    is_priority_purchase = Column(Boolean, default=False)
    source_id = Column(String(100), index=True)  # 原始接口中的 id
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    platform = relationship("Platform", back_populates="launch_calendars")
    ip = relationship("IP", back_populates="launch_calendars")
    detail = relationship("LaunchDetail", back_populates="launch", uselist=False)


class LaunchDetail(Base):
    __tablename__ = "launch_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    launch_id = Column(Integer, ForeignKey("launch_calendar.id"), unique=True, index=True)
    priority_purchase_time = Column(DateTime)
    context_condition = Column(Text)
    status = Column(String(50))
    raw_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    launch = relationship("LaunchCalendar", back_populates="detail")


class Archive(Base):
    __tablename__ = "archives"

    archive_id = Column(String(100), primary_key=True)
    archive_name = Column(String(300), nullable=False)
    total_goods_count = Column(Integer)
    platform_id = Column(Integer, ForeignKey("platforms.id"), index=True)
    ip_id = Column(Integer, ForeignKey("ips.id"), index=True)
    issue_time = Column(DateTime)
    archive_description = Column(Text)
    archive_type = Column(String(50))
    is_hot = Column(Boolean, default=False)
    is_open_auction = Column(Boolean, default=False)
    is_open_want_buy = Column(Boolean, default=False)
    img = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    platform = relationship("Platform", back_populates="archives")
    ip = relationship("IP", back_populates="archives")


class TaskConfig(Base):
    __tablename__ = "task_configs"

    task_id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(String(500))
    schedule_type = Column(String(20), nullable=False, default="interval")
    interval_seconds = Column(Integer)
    cron = Column(String(100))
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs = relationship("TaskRun", back_populates="task")


class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(String(50), ForeignKey("task_configs.task_id"), index=True, nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime)
    duration_ms = Column(Integer)
    message = Column(Text)
    error = Column(Text)

    task = relationship("TaskConfig", back_populates="runs")

    __table_args__ = (
        Index("ix_task_runs_task_started", "task_id", "started_at"),
    )


class TaskRunLog(Base):
    __tablename__ = "task_run_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("task_runs.id"), index=True, nullable=False)
    level = Column(String(20), nullable=False, default="info")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_task_run_logs_run_created", "run_id", "created_at"),
    )


class ArchiveMiss(Base):
    """记录已检查但 API 不存在的 archive_id，避免重复请求"""
    __tablename__ = "archive_misses"

    archive_id = Column(String(100), primary_key=True)
    checked_at = Column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="新对话")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # system / user / assistant / tool
    content = Column(Text)
    tool_calls = Column(Text)  # JSON string of tool_calls array
    tool_call_id = Column(String(100))
    name = Column(String(100))  # tool name for tool role
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )
