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


class JingtanSkuWiki(Base):
    __tablename__ = "jingtan_sku_wikis"

    sku_id = Column(String(50), primary_key=True)
    sku_name = Column(String(300), nullable=False, index=True)
    author = Column(String(200))
    owner = Column(String(300))
    partner = Column(String(50))
    partner_name = Column(String(100))
    first_category = Column(String(50), index=True)
    first_category_name = Column(String(100))
    second_category = Column(String(50), index=True)
    second_category_name = Column(String(100))
    quantity_type = Column(String(50))
    sku_quantity = Column(Integer)
    sku_type = Column(String(50))
    sku_issue_time_ms = Column(BigInteger, index=True)
    sku_producer = Column(String(50))
    mini_file_url = Column(String(500))
    raw_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JingtanSkuHomepageDetail(Base):
    __tablename__ = "jingtan_sku_homepage_details"

    sku_id = Column(String(50), primary_key=True)
    sku_name = Column(String(300), nullable=False, index=True)
    author = Column(String(200))
    owner = Column(String(300))
    partner = Column(String(50))
    partner_name = Column(String(100))
    biz_type = Column(String(50))
    bg_conf = Column(String(50))
    bg_info = Column(String(500))
    has_item = Column(Boolean)
    mini_file_url = Column(String(500))
    origin_file_url = Column(String(500))
    quantity_type = Column(String(50))
    sku_desc = Column(Text)
    sku_desc_image_file_ids = Column(Text)
    sku_issue_time_ms = Column(BigInteger, index=True)
    sku_producer = Column(String(50))
    sku_quantity = Column(Integer)
    sku_type = Column(String(50))
    collect_num = Column(Integer)
    user_collect_status = Column(Boolean)
    comment_num = Column(Integer)
    mini_feed_num = Column(Integer)
    show_comment_list = Column(Boolean)
    show_mini_feed_list = Column(Boolean)
    producer_fans_uid = Column(String(50))
    producer_name = Column(String(200))
    producer_avatar = Column(String(500))
    producer_avatar_type = Column(String(50))
    certification_name = Column(String(100))
    certification_type = Column(String(50))
    follow_status = Column(String(50))
    produce_amount = Column(Integer)
    raw_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Plane(Base):
    __tablename__ = "planes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    img = Column(String(500))
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
