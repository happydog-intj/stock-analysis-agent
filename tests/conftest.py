"""
tests/conftest.py — pytest 全局 Fixture

提供测试用的数据库、Redis、Mock 客户端等基础设施。
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

# 在导入项目代码前，注入测试用环境变量
os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CLAUDE_API_KEY", "test-key-not-real")
os.environ.setdefault("FEISHU_WEBHOOK", "")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """使用 asyncio 作为 anyio 后端。"""
    return "asyncio"


@pytest_asyncio.fixture
async def mock_redis(mocker: Any) -> Any:
    """
    Mock Redis 客户端 Fixture。

    TODO: 使用 fakeredis 提供更真实的内存 Redis 行为
        import fakeredis.aioredis as fakeredis
        return fakeredis.FakeRedis()
    """
    mock = mocker.AsyncMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.setex.return_value = True
    return mock


@pytest.fixture
def sample_sentiment_records() -> list[dict[str, Any]]:
    """示例情绪分析输入数据。"""
    return [
        {
            "platform": "xueqiu",
            "ticker": "1860.HK",
            "external_id": "xq-001",
            "content": "Mintegral 在东南亚市场增速很快，看好汇量科技今年业绩！",
            "author": "test_user_1",
            "captured_at": "2025-03-15T10:00:00+00:00",
        },
        {
            "platform": "reddit",
            "ticker": "1860.HK",
            "external_id": "rd-002",
            "content": "1860.HK seems undervalued compared to AppLovin. Mintegral growing fast.",
            "author": "reddit_user",
            "captured_at": "2025-03-15T09:30:00+00:00",
        },
        {
            "platform": "xueqiu",
            "ticker": "1860.HK",
            "external_id": "xq-003",
            "content": "广告行业整体低迷，汇量科技面临不小压力",
            "author": "test_user_2",
            "captured_at": "2025-03-15T08:00:00+00:00",
        },
    ]


@pytest.fixture
def sample_market_snapshots() -> list[dict[str, Any]]:
    """示例竞对行情快照数据。"""
    return [
        {
            "ticker": "1860.HK",
            "price": 3.15,
            "market_cap": 2_500_000_000,
            "revenue_ttm": 800_000_000,
            "pe_ratio": 18.5,
            "ps_ratio": 3.1,
            "change_pct": -1.5,
            "trade_date": "2025-03-14",
        },
        {
            "ticker": "APP",
            "price": 85.20,
            "market_cap": 45_000_000_000,
            "revenue_ttm": 4_200_000_000,
            "pe_ratio": 42.3,
            "ps_ratio": 10.7,
            "change_pct": 2.3,
            "trade_date": "2025-03-14",
        },
        {
            "ticker": "U",
            "price": 22.50,
            "market_cap": 8_500_000_000,
            "revenue_ttm": 2_100_000_000,
            "pe_ratio": None,
            "ps_ratio": 4.0,
            "change_pct": -0.8,
            "trade_date": "2025-03-14",
        },
    ]
