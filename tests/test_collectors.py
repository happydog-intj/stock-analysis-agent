"""
tests/test_collectors.py — 数据采集器单元测试

覆盖：
  - BaseCollector run_once 异常处理
  - RedditCollector 关键词过滤逻辑
  - HKEXCollector 公告分类逻辑
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.collectors.base import BaseCollector, CollectorError
from src.collectors.hkex import HKEXCollector, classify_announcement
from src.collectors.reddit import RedditCollector

# ── 测试 BaseCollector ────────────────────────────────────────────────────────


class ConcreteCollector(BaseCollector):
    """用于测试的具体采集器实现（最小化 stub）。"""

    platform = "test"

    async def collect(self, since: Any = None) -> list[dict[str, Any]]:
        return []


class TestBaseCollector:
    """BaseCollector 单元测试。"""

    @pytest.fixture
    def collector(self) -> ConcreteCollector:
        return ConcreteCollector()

    @pytest.mark.asyncio
    async def test_run_once_returns_results(
        self, collector: ConcreteCollector, mocker: Any
    ) -> None:
        """测试 run_once 正常返回采集结果。"""
        expected = [{"platform": "test", "content": "hello"}]
        mocker.patch.object(collector, "collect", return_value=expected)
        result = await collector.run_once()
        assert result == expected

    @pytest.mark.asyncio
    async def test_run_once_handles_collector_error(
        self,
        collector: ConcreteCollector,
        mocker: Any,
    ) -> None:
        """测试 run_once 捕获 CollectorError 并返回空列表。"""
        mocker.patch.object(collector, "collect", side_effect=CollectorError("测试错误"))
        result = await collector.run_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_run_once_handles_unexpected_error(
        self,
        collector: ConcreteCollector,
        mocker: Any,
    ) -> None:
        """测试 run_once 捕获未知异常并返回空列表。"""
        mocker.patch.object(collector, "collect", side_effect=RuntimeError("意外错误"))
        result = await collector.run_once()
        assert result == []

    def test_repr(self, collector: ConcreteCollector) -> None:
        """测试 __repr__ 输出格式。"""
        assert repr(collector) == "<ConcreteCollector platform=test>"


# ── 测试 RedditCollector 关键词过滤 ──────────────────────────────────────────


class TestRedditCollector:
    """RedditCollector 单元测试。"""

    @pytest.fixture
    def collector(self) -> RedditCollector:
        return RedditCollector()

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Mobvista is growing fast in Southeast Asia", True),
            ("1860.HK seems undervalued compared to AppLovin", True),
            ("Mintegral DSP performance exceeded expectations", True),
            ("Apple announced new iPhone features today", False),
            ("汇量科技 Q3 业绩超预期", True),
            ("Bitcoin hits new all-time high", False),
        ],
    )
    def test_is_relevant_keyword_filtering(
        self,
        collector: RedditCollector,
        text: str,
        expected: bool,
    ) -> None:
        """测试关键词过滤的准确性。"""
        assert collector._is_relevant(text) == expected

    @pytest.mark.asyncio
    async def test_collect_returns_empty_on_error(
        self,
        collector: RedditCollector,
        mocker: Any,
    ) -> None:
        """测试采集失败时返回空列表。"""
        mocker.patch.object(
            collector,
            "_sync_collect",
            side_effect=Exception("网络错误"),
        )
        result = await collector.run_once()
        assert result == []


# ── 测试 HKEXCollector 公告分类 ──────────────────────────────────────────────


class TestHKEXClassifier:
    """HKEXCollector 公告分类逻辑测试。"""

    @pytest.mark.parametrize(
        "title, expected_type, expected_priority",
        [
            ("汇量科技集团 2024 年度业绩公告", "earnings", 3),
            ("Purchase of Shares under Share Repurchase Mandate", "buyback", 2),
            ("Disclosure of Interests — Director", "shareholding", 2),
            ("Declaration of Special Dividend", "dividend", 2),
            ("Appointment of New Chief Executive Officer", "management", 2),
            ("Closure of Register of Members", "general", 1),
            ("General Meeting Notice", "general", 1),
            ("Profit Warning — Expected Significant Decline", "earnings", 3),
        ],
    )
    def test_classify_announcement(
        self,
        title: str,
        expected_type: str,
        expected_priority: int,
    ) -> None:
        """测试各种公告标题的分类准确性。"""
        ann_type, priority = classify_announcement(title)
        assert ann_type == expected_type, (
            f"标题 '{title}' 期望类型 {expected_type}，实际 {ann_type}"
        )
        assert priority == expected_priority, (
            f"标题 '{title}' 期望优先级 {expected_priority}，实际 {priority}"
        )
