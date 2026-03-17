"""
src/db/database.py — 数据库连接管理

提供 SQLAlchemy 异步引擎、Session 工厂及便捷的 get_session() 依赖注入函数。

用法：
    async with get_session() as session:
        result = await session.execute(select(SentimentRecord))
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import settings
from src.db.models import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """返回（或创建）全局异步引擎。"""
    global _engine
    if _engine is None:
        # SQLite 不支持 pool_size / max_overflow，仅非 SQLite 时传入
        is_sqlite = settings.db_url.startswith("sqlite")
        engine_kwargs: dict = {
            "pool_pre_ping": not is_sqlite,
            "echo": settings.log_level == "DEBUG",
        }
        if not is_sqlite:
            engine_kwargs["pool_size"] = settings.db_pool_size
            engine_kwargs["max_overflow"] = settings.db_max_overflow
        _engine = create_async_engine(settings.db_url, **engine_kwargs)
        logger.info("数据库引擎已创建: %s", settings.db_url.split("@")[-1])
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """返回（或创建）全局 Session 工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    异步上下文管理器，提供带自动事务的 Session。

    示例::
        async with get_session() as session:
            session.add(record)
            await session.commit()
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    初始化数据库：创建所有表（若不存在）。

    生产环境建议使用 Alembic 迁移而非此函数。
    TODO: 集成 Alembic autogenerate
    """
    engine = get_engine()
    async with engine.begin() as conn:
        logger.info("正在初始化数据库表...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库初始化完成。")


async def close_db() -> None:
    """关闭数据库连接池（用于优雅退出）。"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("数据库连接池已关闭。")
