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
    ip_name = Column(String(200), nullable=False)
    ip_avatar = Column(String(500))
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
    market = relationship("ArchiveMarket", back_populates="archive", uselist=False)
    price_history = relationship("ArchivePriceHistory", back_populates="archive")


class ArchiveMarket(Base):
    __tablename__ = "archive_market"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archive_id = Column(String(100), ForeignKey("archives.archive_id"), unique=True, index=True)
    goods_min_price = Column(Float)
    want_buy_count = Column(Integer, default=0)
    selling_count = Column(Integer, default=0)
    deal_count = Column(Integer, default=0)
    want_buy_max_price = Column(Float)
    deal_price = Column(Float)
    record_time = Column(DateTime, default=datetime.utcnow)

    archive = relationship("Archive", back_populates="market")


class ArchivePriceHistory(Base):
    __tablename__ = "archive_price_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    archive_id = Column(String(100), ForeignKey("archives.archive_id"), index=True)
    min_price = Column(Float)
    sell_count = Column(Integer, default=0)
    buy_count = Column(Integer, default=0)
    deal_count = Column(Integer, default=0)
    record_time = Column(DateTime, default=datetime.utcnow)

    archive = relationship("Archive", back_populates="price_history")

    __table_args__ = (
        Index("ix_price_history_archive_time", "archive_id", "record_time"),
    )
