"""
tests/test_sentiment.py — 情绪分析引擎单元测试

覆盖：
  - SentimentAnalyzer 缓存逻辑
  - Claude API Mock 调用
  - 批量分析输入/输出格式验证
  - 情绪标签与分值一致性检查
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.analysis.sentiment import SentimentAnalyzer


class TestSentimentAnalyzer:
    """SentimentAnalyzer 单元测试。"""

    @pytest.fixture
    def analyzer(self) -> SentimentAnalyzer:
        """创建 SentimentAnalyzer 实例。"""
        return SentimentAnalyzer()

    @pytest.fixture
    def mock_claude_response(self) -> dict[str, Any]:
        """Mock Claude API 返回的情绪分析结果。"""
        return {
            "results": [
                {
                    "index": 0,
                    "score": 65,
                    "sentiment": "bullish",
                    "topics": ["Mintegral增速", "东南亚扩张"],
                    "confidence": 0.88,
                    "reasoning": "内容明确表达看好情绪",
                },
                {
                    "index": 1,
                    "score": 50,
                    "sentiment": "bullish",
                    "topics": ["估值洼地", "竞对对比"],
                    "confidence": 0.75,
                    "reasoning": "与竞对相比估值偏低",
                },
                {
                    "index": 2,
                    "score": -30,
                    "sentiment": "bearish",
                    "topics": ["广告行业", "宏观压力"],
                    "confidence": 0.70,
                    "reasoning": "提及行业整体低迷",
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_analyze_batch_returns_enriched_records(
        self,
        analyzer: SentimentAnalyzer,
        sample_sentiment_records: list[dict[str, Any]],
        mock_claude_response: dict[str, Any],
        mocker: Any,
    ) -> None:
        """测试批量分析返回包含情绪字段的增强记录。"""
        # Mock Redis 缓存（全部未命中）
        mock_redis = mocker.AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mocker.patch.object(analyzer, "_get_redis", return_value=mock_redis)

        # Mock Claude API 调用
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_claude_response))]

        mock_client = mocker.AsyncMock()
        mock_client.messages.create.return_value = mock_response
        mocker.patch.object(analyzer, "_get_client", return_value=mock_client)

        results = await analyzer.analyze_batch(sample_sentiment_records)

        assert len(results) == len(sample_sentiment_records)
        for result in results:
            assert "score" in result
            assert "sentiment" in result
            assert "topics" in result
            assert "confidence" in result
            assert "analyzed_at" in result

    @pytest.mark.asyncio
    async def test_analyze_empty_returns_empty(self, analyzer: SentimentAnalyzer) -> None:
        """测试空输入返回空列表。"""
        results = await analyzer.analyze_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(
        self,
        analyzer: SentimentAnalyzer,
        mocker: Any,
    ) -> None:
        """测试缓存命中时不调用 Claude API。"""
        cached_result = {
            "score": 70,
            "sentiment": "bullish",
            "topics": ["cached_topic"],
            "confidence": 0.9,
        }

        # Mock Redis 返回缓存命中
        mock_redis = mocker.AsyncMock()
        mock_redis.get.return_value = json.dumps(cached_result)
        mocker.patch.object(analyzer, "_get_redis", return_value=mock_redis)

        # Mock Claude（不应被调用）
        mock_client = mocker.AsyncMock()
        mocker.patch.object(analyzer, "_get_client", return_value=mock_client)

        records = [{"content": "测试内容", "platform": "xueqiu"}]
        results = await analyzer.analyze_batch(records)

        assert len(results) == 1
        assert results[0]["score"] == 70
        # 验证 Claude API 未被调用
        mock_client.messages.create.assert_not_called()

    def test_cache_key_is_deterministic(self, analyzer: SentimentAnalyzer) -> None:
        """测试相同内容始终生成相同缓存键。"""
        content = "测试内容：汇量科技看涨"
        key1 = analyzer._cache_key(content)
        key2 = analyzer._cache_key(content)
        assert key1 == key2
        assert key1.startswith("sentiment:")

    def test_cache_key_differs_for_different_content(self, analyzer: SentimentAnalyzer) -> None:
        """测试不同内容生成不同缓存键。"""
        key1 = analyzer._cache_key("内容A")
        key2 = analyzer._cache_key("内容B")
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_analyze_single(
        self,
        analyzer: SentimentAnalyzer,
        mocker: Any,
    ) -> None:
        """测试单条分析接口。"""
        mock_result = {"score": 45, "sentiment": "bullish", "topics": [], "confidence": 0.8}

        # Mock analyze_batch
        mocker.patch.object(
            analyzer,
            "analyze_batch",
            return_value=[
                {"content": "test", **mock_result, "analyzed_at": "2025-03-15T10:00:00Z"}
            ],
        )

        result = await analyzer.analyze_single("test")
        assert result["score"] == 45
        assert result["sentiment"] == "bullish"
