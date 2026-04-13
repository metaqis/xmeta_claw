from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, BigInteger, Index,
    Date, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")  # admin / viewer
    created_at = Column(DateTime(timezone=True), default=_now)


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=_now)

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
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    platform = relationship("Platform", back_populates="ips")
    launch_calendars = relationship("LaunchCalendar", back_populates="ip")
    archives = relationship("Archive", back_populates="ip")


class LaunchCalendar(Base):
    __tablename__ = "launch_calendar"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(300), nullable=False)
    sell_time = Column(DateTime(timezone=True), index=True)
    price = Column(Float)
    count = Column(Integer)
    platform_id = Column(Integer, ForeignKey("platforms.id"), index=True)
    ip_id = Column(Integer, ForeignKey("ips.id"), index=True)
    img = Column(String(500))
    priority_purchase_num = Column(Integer, default=0)
    is_priority_purchase = Column(Boolean, default=False)
    source_id = Column(String(100), index=True)  # 原始接口中的 id
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    platform = relationship("Platform", back_populates="launch_calendars")
    ip = relationship("IP", back_populates="launch_calendars")
    detail = relationship("LaunchDetail", back_populates="launch", uselist=False)


class LaunchDetail(Base):
    __tablename__ = "launch_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    launch_id = Column(Integer, ForeignKey("launch_calendar.id"), unique=True, index=True)
    priority_purchase_time = Column(DateTime(timezone=True))
    context_condition = Column(Text)
    status = Column(String(50))
    raw_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now)

    launch = relationship("LaunchCalendar", back_populates="detail")


class Archive(Base):
    __tablename__ = "archives"

    archive_id = Column(String(100), primary_key=True)
    archive_name = Column(String(300), nullable=False)
    total_goods_count = Column(Integer)
    platform_id = Column(Integer, ForeignKey("platforms.id"), index=True)
    ip_id = Column(Integer, ForeignKey("ips.id"), index=True)
    issue_time = Column(DateTime(timezone=True))
    archive_description = Column(Text)
    archive_type = Column(String(50))
    is_hot = Column(Boolean, default=False)
    is_open_auction = Column(Boolean, default=False)
    is_open_want_buy = Column(Boolean, default=False)
    img = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

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
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


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
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class Plane(Base):
    __tablename__ = "planes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    img = Column(String(500))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class TaskConfig(Base):
    __tablename__ = "task_configs"

    task_id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(String(500))
    schedule_type = Column(String(20), nullable=False, default="interval")
    interval_seconds = Column(Integer)
    cron = Column(String(100))
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    runs = relationship("TaskRun", back_populates="task")


class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(String(50), ForeignKey("task_configs.task_id"), index=True, nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), default=_now, index=True)
    finished_at = Column(DateTime(timezone=True))
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
    created_at = Column(DateTime(timezone=True), default=_now, index=True)

    __table_args__ = (
        Index("ix_task_run_logs_run_created", "run_id", "created_at"),
    )


class ArchiveMiss(Base):
    """记录已检查但 API 不存在的 archive_id，避免重复请求"""
    __tablename__ = "archive_misses"

    archive_id = Column(String(100), primary_key=True)
    checked_at = Column(DateTime(timezone=True), default=_now)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="新对话")
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

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
    created_at = Column(DateTime(timezone=True), default=_now)

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )


class Article(Base):
    """自动生成的微信公众号文章"""
    __tablename__ = "articles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False)
    article_type = Column(String(20), nullable=False, index=True)  # daily / weekly / monthly
    data_date = Column(String(50), index=True)
    summary = Column(String(500))
    content_html = Column(Text)
    content_markdown = Column(Text)
    cover_image_url = Column(String(500))
    analysis_data = Column(Text)  # raw analysis data JSON
    status = Column(String(20), nullable=False, default="draft", index=True)  # generating/draft/publishing/published/failed
    wechat_media_id = Column(String(200))
    wechat_publish_id = Column(String(200))
    error_message = Column(Text)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    images = relationship("ArticleImage", back_populates="article", cascade="all, delete-orphan")


class ArticleImage(Base):
    """文章配图（图表 / 封面）"""
    __tablename__ = "article_images"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    article_id = Column(BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    image_type = Column(String(50))  # cover / daily_trend / platform_pie / ...
    file_path = Column(String(500))
    wechat_media_url = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=_now)

    article = relationship("Article", back_populates="images")


class MarketDailySummary(Base):
    """市场每日全局汇总快照"""
    __tablename__ = "market_daily_summaries"

    stat_date = Column(Date, primary_key=True)          # 统计日期 (YYYY-MM-DD)
    total_deal_count = Column(Integer)                  # 全市场总成交笔数
    total_market_value = Column(Float)                  # 全市场总市值
    total_deal_amount = Column(Float)                   # 全市场总成交额
    active_plane_count = Column(Integer)                # 有成交的板块数
    top_plane_name = Column(String(100))                # 成交量最高板块
    top_plane_deal_count = Column(Integer)              # 最高板块成交量
    top_ip_name = Column(String(200))                   # 成交量最高 IP
    top_ip_deal_count = Column(Integer)                 # 最高 IP 成交量
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class MarketPlaneSnapshot(Base):
    """板块每日市场快照"""
    __tablename__ = "market_plane_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    plane_source_id = Column(Integer)                   # planes.source_id (xmeta内部id)
    plane_code = Column(String(50), nullable=False)     # 板块编码
    plane_name = Column(String(100), nullable=False)    # 板块名称
    avg_price = Column(Float)                           # 均价日涨跌幅 %
    deal_price = Column(Float)                          # 最新成交价
    deal_count = Column(Integer)                        # 今日成交量
    shelves_rate = Column(Float)                        # 挂售率
    total_market_value = Column(Float)                  # 总市值
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("stat_date", "plane_code", name="uq_plane_snapshot_date_code"),
        Index("ix_plane_snapshot_date", "stat_date"),
    )


class MarketIPSnapshot(Base):
    """IP 方每日市场快照（取接口返回的 Top N）"""
    __tablename__ = "market_ip_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    community_ip_id = Column(Integer, nullable=False)   # xmeta communityIpId
    name = Column(String(200), nullable=False)
    avatar = Column(String(500))
    rank = Column(Integer)                              # 榜单排名 (1-based)
    archive_count = Column(Integer)                     # 藏品数量
    market_amount = Column(Float)                       # 总市值
    market_amount_rate = Column(Float)                  # 总市值日涨跌幅 %
    hot = Column(Float)                                 # 热度指数
    hot_rate = Column(Float)                            # 热度变化 %
    avg_amount = Column(Float)                          # 均价
    avg_amount_rate = Column(Float)                     # 均价变化 %
    deal_count = Column(Integer)                        # 成交量
    deal_count_rate = Column(Float)                     # 成交量变化 %
    publish_count = Column(Integer)                     # 总发行量
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("stat_date", "community_ip_id", name="uq_ip_snapshot_date_ip"),
        Index("ix_ip_snapshot_date", "stat_date"),
    )


class MarketArchiveSnapshot(Base):
    """热门藏品每日排名快照（按行情分类）"""
    __tablename__ = "market_archive_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    top_code = Column(String(50), nullable=False)       # 分类编码 (e.g. "759475")
    top_name = Column(String(100), nullable=False)      # 分类名称 (e.g. "鲸探50")
    rank = Column(Integer, nullable=False)              # 排名 (1-based)
    archive_id = Column(Integer, nullable=False)
    archive_name = Column(String(300))
    archive_img = Column(String(500))
    selling_count = Column(Integer)                     # 在售数量
    deal_count = Column(Integer)                        # 成交量
    market_amount = Column(Float)                       # 总市值
    market_amount_rate = Column(Float)                  # 市值日涨跌 %
    min_amount = Column(Float)                          # 最低价
    min_amount_rate = Column(Float)                     # 最低价变化 %
    avg_amount = Column(Float)                          # 均价
    avg_amount_rate = Column(Float)                     # 均价变化 %
    up_rate = Column(Float)                             # 上架率
    deal_amount = Column(Float)                         # 成交额
    deal_amount_rate = Column(Float)                    # 成交额变化 %
    publish_count = Column(Integer)                     # 发行量
    platform_id = Column(Integer)
    is_transfer = Column(Boolean)                       # 是否可转让
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint(
            "stat_date", "top_code", "archive_id",
            name="uq_archive_snapshot_date_code_id",
        ),
        Index("ix_archive_snapshot_date_code", "stat_date", "top_code"),
    )


class MarketPlaneCensus(Base):
    """板块每日成交详细统计（涨跌分布）— 来自 /h5/market/censusPlaneArchive"""
    __tablename__ = "market_plane_census"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    plane_code = Column(String(50), nullable=False)     # 板块编码
    plane_name = Column(String(100))                    # 板块名称
    total_market_amount = Column(Float)                 # 总市值
    total_market_amount_rate = Column(Float)            # 总市值日涨跌幅 %
    total_deal_count = Column(Integer)                  # 今日成交量
    total_deal_count_rate = Column(Float)               # 成交量日变化 %
    total_archive_count = Column(Integer)               # 板块藏品总数
    up_archive_count = Column(Integer)                  # 今日上涨藏品数
    down_archive_count = Column(Integer)                # 今日下跌藏品数
    up_down_json = Column(Text)                         # upDownList JSON 字符串
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("stat_date", "plane_code", name="uq_plane_census_date_code"),
        Index("ix_plane_census_date", "stat_date"),
    )


class MarketTopCensus(Base):
    """行情分类每日成交详细统计（涨跌分布）— 来自 /h5/market/censusArchiveTop"""
    __tablename__ = "market_top_census"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    top_code = Column(String(50), nullable=False)       # 分类编码
    top_name = Column(String(100))                      # 分类名称
    total_market_amount = Column(Float)                 # 总市值
    total_market_amount_rate = Column(Float)            # 总市值日涨跌幅 %
    total_deal_count = Column(Integer)                  # 今日成交量
    total_deal_count_rate = Column(Float)               # 成交量日变化 %
    total_archive_count = Column(Integer)               # 分类藏品总数
    up_archive_count = Column(Integer)                  # 今日上涨藏品数
    down_archive_count = Column(Integer)                # 今日下跌藏品数
    up_down_json = Column(Text)                         # upDownList JSON 字符串
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("stat_date", "top_code", name="uq_top_census_date_code"),
        Index("ix_top_census_date", "stat_date"),
    )

