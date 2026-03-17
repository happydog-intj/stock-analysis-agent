"""
src/agents/orchestrator.py — 主编排 Agent

负责协调整个数据流水线：
  采集 → 情绪分析 → 财务分析 → 生成报告 → 推送飞书

每次报告触发时（晨报/午报/收盘报）由调度器调用 run_report()。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timezone


def _parse_dt(val: str | datetime | None, default: datetime | None = None) -> datetime:
    """将 ISO 字符串或 datetime 对象统一转换为 datetime；None 时返回 default 或 now()。"""
    if val is None:
        return default if default is not None else datetime.now(UTC)
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except ValueError:
        return default if default is not None else datetime.now(UTC)
from typing import Any

from config.settings import settings
from src.analysis.competitor import CompetitorAnalyzer
from src.analysis.financial import FinancialAnalyzer
from src.analysis.sentiment import SentimentAnalyzer
from src.collectors.hkex import HKEXCollector
from src.collectors.reddit import RedditCollector
from src.collectors.xueqiu import XueqiuCollector
from src.collectors.yahoo_finance import YahooFinanceCollector
# DB layer removed — stateless design for GitHub Actions (in-memory SQLite had no persistence value)
from src.reporters.feishu import FeishuReporter

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    主编排器：协调所有 Agent 和 Collector 完成一次完整的分析流程。

    使用方式::
        orchestrator = Orchestrator()
        await orchestrator.run_report(period="morning")
    """

    def __init__(self) -> None:
        # 采集器
        self.xueqiu = XueqiuCollector()
        self.reddit = RedditCollector()
        self.hkex = HKEXCollector()
        self.yahoo = YahooFinanceCollector()

        # 分析器
        self.sentiment_analyzer = SentimentAnalyzer()
        self.financial_analyzer = FinancialAnalyzer()
        self.competitor_analyzer = CompetitorAnalyzer()

        # 报告推送
        self.reporter = FeishuReporter()

    async def collect_all(self) -> dict[str, list[dict[str, Any]]]:
        """
        并行执行所有采集器。

        Returns:
            各采集器的结果字典，key 为平台名。

        TODO: 使用 asyncio.gather 并行化采集
        TODO: 添加超时控制（每个采集器最多 60s）
        """
        results: dict[str, list[dict[str, Any]]] = {}

        for collector, name in [
            (self.xueqiu, "xueqiu"),
            (self.reddit, "reddit"),
            (self.hkex, "hkex"),
            (self.yahoo, "yahoo_finance"),
        ]:
            logger.info("开始采集: %s", name)
            data = await collector.run_once()
            results[name] = data

        return results

    async def save_sentiment_records(
        self,
        records: list[dict[str, Any]],
    ) -> None:
        """无状态模式：仅记录日志，不持久化。"""
        logger.info("情绪记录（无持久化）: %d 条", len(records))

    async def save_competitor_snapshots(
        self,
        snapshots: list[dict[str, Any]],
    ) -> None:
        """无状态模式：仅记录日志，不持久化。"""
        logger.info("竞对快照（无持久化）: %d 条", len(snapshots))

    async def save_announcements(
        self,
        announcements: list[dict[str, Any]],
    ) -> None:
        """无状态模式：仅记录日志，不持久化。"""
        logger.info("保存 %d 条公告", len(announcements))

    async def build_snapshot(
        self,
        period: str,
        sentiment_records: list[dict[str, Any]],
        market_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """构建当前时段的情绪快照（无状态，返回 dict）。"""
        scores = [r["score"] for r in sentiment_records if r.get("score") is not None]
        sentiment_avg = sum(scores) / len(scores) if scores else None

        sentiment_dist: dict[str, int] = {}
        for r in sentiment_records:
            label = r.get("sentiment", "neutral")
            if label:
                sentiment_dist[label] = sentiment_dist.get(label, 0) + 1

        topic_counts: dict[str, int] = {}
        for r in sentiment_records:
            for topic in r.get("topics") or []:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        top_topics = sorted(
            [{"topic": t, "count": c} for t, c in topic_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        primary_data = next(
            (d for d in market_data if d.get("ticker") == settings.primary_ticker),
            {},
        )

        return {
            "period": period,
            "ticker": settings.primary_ticker,
            "sentiment_avg": round(sentiment_avg, 2) if sentiment_avg is not None else None,
            "sentiment_dist": sentiment_dist,
            "top_topics": top_topics,
            "sample_count": len(sentiment_records),
            "price": primary_data.get("price"),
            "volume": primary_data.get("volume"),
            "change_pct": primary_data.get("change_pct"),
        }

    async def run_report(self, period: str = "morning") -> None:
        """
        执行完整的数据采集 → 分析 → 报告流程。

        Args:
            period: 报告时段，取值 "morning" / "noon" / "close"

        TODO: 添加分布式锁防止并发执行
        TODO: 记录每次运行的耗时和状态到 DB
        """
        logger.info("=" * 60)
        logger.info("开始 %s 报告流程", period)
        start_time = datetime.now(UTC)

        # 1. 采集数据
        collected = await self.collect_all()
        sentiment_raw = collected.get("xueqiu", []) + collected.get("reddit", [])
        market_data = collected.get("yahoo_finance", [])
        announcements = collected.get("hkex", [])

        # 2. 情绪分析
        sentiment_records = await self.sentiment_analyzer.analyze_batch(sentiment_raw)

        # 3. 竞对分析
        competitor_comparisons = self.competitor_analyzer.build_comparison_table(market_data)
        primary = next(
            (c for c in competitor_comparisons if c.ticker == settings.primary_ticker),
            None,
        )
        peers = [c for c in competitor_comparisons if c.ticker != settings.primary_ticker]
        divergence_signals = (
            self.competitor_analyzer.find_divergence_signals(primary, peers) if primary else []
        )

        # 4. 财务分析（主标的）
        primary_snapshot = next(
            (d for d in market_data if d.get("ticker") == settings.primary_ticker),
            {},
        )
        financial_metrics = self.financial_analyzer.compute_metrics(primary_snapshot)

        # 5. 持久化
        await self.save_sentiment_records(sentiment_records)
        await self.save_competitor_snapshots(market_data)
        await self.save_announcements(announcements)

        snapshot = await self.build_snapshot(period, sentiment_records, market_data)

        # 6. 推送飞书报告
        report_data = {
            "period": period,
            "snapshot": snapshot,
            "sentiment_records": sentiment_records[:5],  # 取最具代表性的 5 条
            "competitor_table": self.competitor_analyzer.format_table_rows(competitor_comparisons),
            "divergence_signals": divergence_signals,
            "financial": self.financial_analyzer.format_for_report(financial_metrics),
            "announcements": announcements,
        }
        await self.reporter.send_report(report_data)

        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        logger.info("%s 报告流程完成，耗时 %.1fs", period, elapsed)

    async def close(self) -> None:
        """关闭所有资源。"""
        await self.xueqiu.close()
        await self.reddit.close()
        await self.hkex.close()
        await self.yahoo.close()
        await self.sentiment_analyzer.close()
