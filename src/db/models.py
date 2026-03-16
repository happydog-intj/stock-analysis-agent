"""
src/db/models.py — SQLAlchemy ORM 数据模型

定义四张核心业务表：
  - SentimentRecord   舆情评论情绪记录
  - DailySnapshot     每日情绪快照
  - Announcement      港交所公告
  - CompetitorSnapshot 竞对行情快照
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


# ── 枚举类型 ──────────────────────────────────────────────────────────────────

class SentimentLabel(str, enum.Enum):
    """情绪标签。"""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


class Platform(str, enum.Enum):
    """数据来源平台。"""
    XUEQIU = "xueqiu"
    REDDIT = "reddit"
    FUTU = "futu"
    TIGER = "tiger"
    WEIBO = "weibo"
    OTHER = "other"


class ReportPeriod(str, enum.Enum):
    """报告周期。"""
    MORNING = "morning"
    NOON = "noon"
    CLOSE = "close"
    DAILY = "daily"


class AnnouncementType(str, enum.Enum):
    """港交所公告类型。"""
    EARNINGS = "earnings"
    BUYBACK = "buyback"
    SHAREHOLDING = "shareholding"
    DIVIDEND = "dividend"
    MANAGEMENT = "management"
    GENERAL = "general"


class AnnouncementPriority(int, enum.Enum):
    """公告优先级（数字越大越重要）。"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


# ── SentimentRecord ───────────────────────────────────────────────────────────

class SentimentRecord(Base):
    """
    单条评论/帖子的情绪分析结果。

    每次从雪球、Reddit 等平台采集到评论后，调用 Claude 分析并写入此表。
    """

    __tablename__ = "sentiment_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(
        Enum(Platform, name="platform_enum"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="平台原始内容 ID（用于去重）"
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)

    score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="情绪分 -100 ~ 100"
    )
    sentiment: Mapped[str | None] = mapped_column(
        Enum(SentimentLabel, name="sentiment_label_enum"), nullable=True
    )
    topics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Claude 提取的主题列表"
    )
    confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="分析置信度 0~1"
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_sentiment_ticker_platform_captured", "ticker", "platform", "captured_at"),
        Index("ix_sentiment_external_id", "platform", "external_id", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<SentimentRecord id={self.id} platform={self.platform} "
            f"ticker={self.ticker} score={self.score}>"
        )


# ── DailySnapshot ─────────────────────────────────────────────────────────────

class DailySnapshot(Base):
    """按标的 + 时段聚合的情绪快照，每天生成三次（晨/午/收盘）。"""

    __tablename__ = "daily_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    period: Mapped[str] = mapped_column(
        Enum(ReportPeriod, name="report_period_enum"),
        nullable=False,
        comment="报告时段：morning/noon/close/daily",
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    sentiment_avg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="时段内情绪分均值"
    )
    sentiment_dist: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="情绪分布"
    )
    top_topics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="热门话题及频次"
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="涨跌幅 %")

    __table_args__ = (
        Index("ix_snapshot_ticker_period_time", "ticker", "period", "snapshot_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<DailySnapshot id={self.id} ticker={self.ticker} "
            f"period={self.period} avg={self.sentiment_avg}>"
        )


# ── Announcement ─────────────────────────────────────────────────────────────

class Announcement(Base):
    """港交所披露易公告记录。"""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    announcement_type: Mapped[str] = mapped_column(
        Enum(AnnouncementType, name="announcement_type_enum"),
        nullable=False,
        default=AnnouncementType.GENERAL,
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=AnnouncementPriority.LOW, comment="1=低 2=中 3=高"
    )

    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_announcement_ticker_published", "ticker", "published_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Announcement id={self.id} ticker={self.ticker} "
            f"type={self.announcement_type} priority={self.priority}>"
        )


# ── CompetitorSnapshot ───────────────────────────────────────────────────────

class CompetitorSnapshot(Base):
    """
    竞对标的（APP / U / APPS）及主标的（1860.HK）的行情快照。

    每日收盘后由 YahooFinanceCollector 写入，用于竞对对比分析。
    """

    __tablename__ = "competitor_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="收盘价")
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="日涨跌幅 %")

    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True, comment="市值（USD）")
    revenue_ttm: Mapped[float | None] = mapped_column(Float, nullable=True, comment="TTM 营收（USD）")
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True, comment="市盈率 PE")
    ps_ratio: Mapped[float | None] = mapped_column(Float, nullable=True, comment="市销率 PS")

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    trade_date: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="交易日期 YYYY-MM-DD"
    )

    __table_args__ = (
        Index("ix_competitor_ticker_date", "ticker", "trade_date", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<CompetitorSnapshot id={self.id} ticker={self.ticker} "
            f"price={self.price} cap={self.market_cap}>"
        )
