"""
src/agents/financial_agent.py — 财务分析 Agent

专注于汇量科技的财务数据分析：
  - 从 competitor_snapshots 表读取最新财务数据
  - 与历史数据对比，计算同比/环比变化
  - 识别关键财务风险信号
  - 为报告提供结构化财务摘要

TODO: 接入港交所公告解析，从年报/季报中提取精确财务数据
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from config.settings import settings
from src.analysis.financial import FinancialAnalyzer
from src.db.database import get_session
from src.db.models import CompetitorSnapshot

logger = logging.getLogger(__name__)


class FinancialAgent:
    """
    财务分析 Agent。

    从 DB 读取最新行情快照并调用 FinancialAnalyzer 生成财务摘要。
    """

    def __init__(self) -> None:
        self.analyzer = FinancialAnalyzer()

    async def get_latest_snapshot(self, ticker: str) -> dict[str, Any] | None:
        """
        从 DB 读取指定标的的最新行情快照。

        Args:
            ticker: 标的代码

        Returns:
            最新快照字典，无数据返回 None

        TODO: 添加 trade_date 过滤，仅取最近交易日的数据
        """
        async with get_session() as session:
            result = await session.execute(
                select(CompetitorSnapshot)
                .where(CompetitorSnapshot.ticker == ticker)
                .order_by(CompetitorSnapshot.captured_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "ticker": row.ticker,
                "price": row.price,
                "market_cap": row.market_cap,
                "revenue_ttm": row.revenue_ttm,
                "pe_ratio": row.pe_ratio,
                "ps_ratio": row.ps_ratio,
                "change_pct": row.change_pct,
                "trade_date": row.trade_date,
            }

    async def run(self) -> dict[str, Any]:
        """
        执行财务分析，返回格式化后的财务摘要。

        Returns:
            财务分析结果字典，供 Orchestrator 组装报告使用

        TODO: 读取前一期快照计算同比指标
        """
        snapshot = await self.get_latest_snapshot(settings.primary_ticker)
        if not snapshot:
            logger.warning("FinancialAgent: 无 %s 快照数据", settings.primary_ticker)
            return {"error": "无行情数据"}

        metrics = self.analyzer.compute_metrics(snapshot)
        return self.analyzer.format_for_report(metrics)
