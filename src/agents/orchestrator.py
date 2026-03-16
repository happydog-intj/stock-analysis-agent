"""
src/agents/orchestrator.py — 主编排 Agent

负责协调整个数据流水线：
  采集 → 情绪分析 → 财务分析 → 生成报告 → 推送飞书

每次报告触发时（晨报/午报/收盘报）由调度器调用 run_report()。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from src.analysis.competitor import CompetitorAnalyzer
from src.analysis.financial import FinancialAnalyzer
from src.analysis.sentiment import SentimentAnalyzer
from src.collectors.hkex import HKEXCollector
from src.collectors.reddit import RedditCollector
from src.collectors.xueqiu import XueqiuCollector
from src.collectors.yahoo_finance import YahooFinanceCollector
from src.db.database import get_session
from src.db.models import (
    Announcement,
    CompetitorSnapshot,
    DailySnapshot,
    ReportPeriod,
    SentimentRecord,
)
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
        """
        将情绪分析结果写入 sentiment_records 表。

        TODO: 使用 upsert（ON CONFLICT DO UPDATE）避免重复插入
        """
        if not records:
            return

        async with get_session() as session:
            for r in records:
                record = SentimentRecord(
                    platform=r.get("platform", "other"),
                    ticker=r.get("ticker", settings.primary_ticker),
                    external_id=r.get("external_id"),
                    content=r.get("content", ""),
                    author=r.get("author"),
                    score=r.get("score"),
                    sentiment=r.get("sentiment"),
                    topics=r.get("topics"),
                    confidence=r.get("confidence"),
                    captured_at=r.get("captured_at", datetime.now(timezone.utc)),
                )
                session.add(record)
        logger.info("保存 %d 条情绪记录", len(records))

    async def save_competitor_snapshots(
        self,
        snapshots: list[dict[str, Any]],
    ) -> None:
        """
        将竞对行情快照写入 competitor_snapshots 表。

        TODO: 使用 upsert by (ticker, trade_date)
        """
        if not snapshots:
            return

        async with get_session() as session:
            for s in snapshots:
                snapshot = CompetitorSnapshot(
                    ticker=s.get("ticker", ""),
                    price=s.get("price"),
                    open_price=s.get("open_price"),
                    high_price=s.get("high_price"),
                    low_price=s.get("low_price"),
                    volume=s.get("volume"),
                    change_pct=s.get("change_pct"),
                    market_cap=s.get("market_cap"),
                    revenue_ttm=s.get("revenue_ttm"),
                    pe_ratio=s.get("pe_ratio"),
                    ps_ratio=s.get("ps_ratio"),
                    trade_date=s.get("trade_date"),
                )
                session.add(snapshot)
        logger.info("保存 %d 条竞对快照", len(snapshots))

    async def save_announcements(
        self,
        announcements: list[dict[str, Any]],
    ) -> None:
        """
        将港交所公告写入 announcements 表。

        TODO: 高优先级公告（P3）立即触发 alert
        """
        if not announcements:
            return

        async with get_session() as session:
            for a in announcements:
                ann = Announcement(
                    ticker=a.get("ticker", settings.primary_ticker),
                    title=a.get("title", ""),
                    announcement_type=a.get("announcement_type", "general"),
                    priority=a.get("priority", 1),
                    url=a.get("url"),
                    published_at=a.get("published_at", datetime.now(timezone.utc)),
                )
                session.add(ann)
        logger.info("保存 %d 条公告", len(announcements))

    async def build_snapshot(
        self,
        period: str,
        sentiment_records: list[dict[str, Any]],
        market_data: list[dict[str, Any]],
    ) -> DailySnapshot:
        """
        构建当前时段的情绪快照。

        TODO: 从 DB 读取指定时间窗口内的所有记录计算聚合指标
        TODO: 计算 sentiment_dist（各情绪标签的分布）
        """
        scores = [
            r["score"] for r in sentiment_records
            if r.get("score") is not None
        ]
        sentiment_avg = sum(scores) / len(scores) if scores else None

        # 统计情绪分布
        sentiment_dist: dict[str, int] = {}
        for r in sentiment_records:
            label = r.get("sentiment", "neutral")
            if label:
                sentiment_dist[label] = sentiment_dist.get(label, 0) + 1

        # 提取热门话题
        topic_counts: dict[str, int] = {}
        for r in sentiment_records:
            for topic in (r.get("topics") or []):
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        top_topics = sorted(
            [{"topic": t, "count": c} for t, c in topic_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        # 获取主标的最新价格
        primary_data = next(
            (d for d in market_data if d.get("ticker") == settings.primary_ticker),
            {},
        )

        return DailySnapshot(
            period=period,
            ticker=settings.primary_ticker,
            sentiment_avg=round(sentiment_avg, 2) if sentiment_avg is not None else None,
            sentiment_dist=sentiment_dist,
            top_topics=top_topics,
            sample_count=len(sentiment_records),
            price=primary_data.get("price"),
            volume=primary_data.get("volume"),
            change_pct=primary_data.get("change_pct"),
        )

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
        start_time = datetime.now(timezone.utc)

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
            self.competitor_analyzer.find_divergence_signals(primary, peers)
            if primary else []
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
        async with get_session() as session:
            session.add(snapshot)

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

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("%s 报告流程完成，耗时 %.1fs", period, elapsed)

    async def close(self) -> None:
        """关闭所有资源。"""
        await self.xueqiu.close()
        await self.reddit.close()
        await self.hkex.close()
        await self.yahoo.close()
        await self.sentiment_analyzer.close()
