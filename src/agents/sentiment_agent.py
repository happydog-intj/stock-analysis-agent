"""
src/agents/sentiment_agent.py — 情绪分析 Agent

独立运行的情绪分析子 Agent，专注于：
  1. 从 DB 读取未分析的评论（score IS NULL）
  2. 批量调用 SentimentAnalyzer 分析
  3. 将结果回写到 DB

设计为可独立运行，也可由 Orchestrator 调用。
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update

from src.analysis.sentiment import SentimentAnalyzer
from src.db.database import get_session
from src.db.models import SentimentRecord

logger = logging.getLogger(__name__)


class SentimentAgent:
    """
    情绪分析 Agent。

    轮询 sentiment_records 表中 score IS NULL 的记录，
    批量送入 Claude 分析后更新结果。
    """

    def __init__(self) -> None:
        self.analyzer = SentimentAnalyzer()

    async def run(self, batch_limit: int = 50) -> int:
        """
        执行一轮情绪分析。

        Args:
            batch_limit: 本次最多处理多少条未分析记录

        Returns:
            实际处理的记录数

        TODO: 实现分布式锁，防止多实例并发分析同一批记录
        TODO: 支持按优先级排序（高优先级公告关联评论优先分析）
        """
        async with get_session() as session:
            # 读取未分析记录
            result = await session.execute(
                select(SentimentRecord)
                .where(SentimentRecord.score.is_(None))
                .order_by(SentimentRecord.captured_at.asc())
                .limit(batch_limit)
            )
            pending: list[SentimentRecord] = list(result.scalars().all())

        if not pending:
            logger.info("SentimentAgent: 无待分析记录")
            return 0

        logger.info("SentimentAgent: 处理 %d 条记录", len(pending))

        # 转换为分析器所需格式
        inputs = [
            {"content": r.content, "_id": r.id}
            for r in pending
        ]
        analyzed = await self.analyzer.analyze_batch(inputs)

        # 回写分析结果
        async with get_session() as session:
            for result_item in analyzed:
                record_id = result_item.get("_id")
                if not record_id:
                    continue
                await session.execute(
                    update(SentimentRecord)
                    .where(SentimentRecord.id == record_id)
                    .values(
                        score=result_item.get("score"),
                        sentiment=result_item.get("sentiment"),
                        topics=result_item.get("topics"),
                        confidence=result_item.get("confidence"),
                        analyzed_at=result_item.get("analyzed_at"),
                    )
                )

        logger.info("SentimentAgent: 完成 %d 条分析", len(analyzed))
        return len(analyzed)

    async def close(self) -> None:
        """释放资源。"""
        await self.analyzer.close()
