"""
SQLAlchemy ORM 模型定义。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Float, Integer, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SentimentRecord(Base):
    """评论情绪记录表。"""
    __tablename__ = "sentiment_records"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform:     Mapped[str]      = mapped_column(String(32), nullable=False, index=True)
    ticker:       Mapped[str]      = mapped_column(String(16), nullable=False, index=True)
    content:      Mapped[str]      = mapped_column(Text, nullable=False)
    score:        Mapped[float]    = mapped_column(Float, nullable=False)         # -100 ~ 100
    sentiment:    Mapped[str]      = mapped_column(String(16), nullable=False)    # bullish/neutral/bearish
    topics:       Mapped[dict]     = mapped_column(JSONB, nullable=False, default=list)
    confidence:   Mapped[float]    = mapped_column(Float, nullable=False, default=0.5)
    captured_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_sentiment_platform_ticker_time", "platform", "ticker", "captured_at"),
    )


class DailySnapshot(Base):
    """每次报告的情绪快照。"""
    __tablename__ = "daily_snapshots"

    id:               Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_time:    Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period:           Mapped[str]   = mapped_column(String(16), nullable=False)   # morning/noon/close
    ticker:           Mapped[str]   = mapped_column(String(16), nullable=False)
    sentiment_avg:    Mapped[float] = mapped_column(Float, nullable=True)
    sentiment_dist:   Mapped[dict]  = mapped_column(JSONB, nullable=True)         # {bullish:N, neutral:N, bearish:N}
    top_topics:       Mapped[dict]  = mapped_column(JSONB, nullable=True)
    price:            Mapped[float] = mapped_column(Float, nullable=True)
    change_pct:       Mapped[float] = mapped_column(Float, nullable=True)
    volume:           Mapped[int]   = mapped_column(BigInteger, nullable=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_snapshot_ticker_time", "ticker", "snapshot_time"),
    )


class Announcement(Base):
    """港交所公告记录。"""
    __tablename__ = "announcements"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker:       Mapped[str]      = mapped_column(String(16), nullable=False, index=True)
    doc_id:       Mapped[str]      = mapped_column(String(64), nullable=False, unique=True)
    title:        Mapped[str]      = mapped_column(Text, nullable=False)
    type:         Mapped[str]      = mapped_column(String(32), nullable=False)
    priority:     Mapped[str]      = mapped_column(String(16), nullable=False, index=True)
    url:          Mapped[str]      = mapped_column(Text, nullable=True)
    content:      Mapped[str]      = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CompetitorSnapshot(Base):
    """竞对每日行情快照。"""
    __tablename__ = "competitor_snapshots"

    id:           Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker:       Mapped[str]   = mapped_column(String(16), nullable=False, index=True)
    name:         Mapped[str]   = mapped_column(String(64), nullable=True)
    price:        Mapped[float] = mapped_column(Float, nullable=True)
    change_pct:   Mapped[float] = mapped_column(Float, nullable=True)
    market_cap:   Mapped[float] = mapped_column(Float, nullable=True)
    pe_ratio:     Mapped[float] = mapped_column(Float, nullable=True)
    revenue_ttm:  Mapped[float] = mapped_column(Float, nullable=True)
    volume:       Mapped[int]   = mapped_column(BigInteger, nullable=True)
    captured_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_competitor_ticker_date", "ticker", "captured_at"),
    )
