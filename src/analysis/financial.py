"""
src/analysis/financial.py — 财务指标分析模块

汇总汇量科技的关键财务指标，计算同比/环比变化，
识别异常信号（如营收增速骤降、毛利率异常波动等）。

数据来源：
  - Yahoo Finance（基础指标：PE/PS/市值/营收）
  - 港交所公告（季报/年报数字，需人工或 LLM 提取）

TODO: 接入专业财务数据 API（如 Refinitiv / Bloomberg / Wind）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FinancialMetrics:
    """
    汇量科技关键财务指标快照。

    所有金额字段单位：USD（美元）
    """

    ticker: str = "1860.HK"

    # 市场数据
    price: float | None = None
    market_cap: float | None = None
    change_pct_1d: float | None = None

    # 估值
    pe_ratio: float | None = None
    ps_ratio: float | None = None
    pb_ratio: float | None = None

    # 营收（TTM）
    revenue_ttm: float | None = None
    revenue_growth_yoy: float | None = None  # 同比增速（%）

    # 毛利润
    gross_profit_ttm: float | None = None
    gross_margin: float | None = None  # 毛利率（%）

    # 净利润
    net_income_ttm: float | None = None
    net_margin: float | None = None  # 净利率（%）

    # 风险信号
    risk_signals: list[str] = field(default_factory=list)


class FinancialAnalyzer:
    """
    财务指标分析器。

    从竞对行情快照（CompetitorSnapshot）和公告摘要中计算关键指标，
    识别潜在风险信号。
    """

    def __init__(self) -> None:
        pass

    def compute_metrics(
        self,
        snapshot: dict[str, Any],
        prev_snapshot: dict[str, Any] | None = None,
    ) -> FinancialMetrics:
        """
        计算并返回财务指标快照。

        Args:
            snapshot:       最新竞对行情快照字典
            prev_snapshot:  上一期快照（用于计算同比/环比变化），可为 None

        Returns:
            FinancialMetrics 数据类实例

        TODO: 从 DB 读取历史快照计算 YoY
        TODO: 接入年报/季报解析以获取毛利率等精确数据
        """
        metrics = FinancialMetrics(ticker=snapshot.get("ticker", "1860.HK"))
        metrics.price = snapshot.get("price")
        metrics.market_cap = snapshot.get("market_cap")
        metrics.change_pct_1d = snapshot.get("change_pct")
        metrics.pe_ratio = snapshot.get("pe_ratio")
        metrics.ps_ratio = snapshot.get("ps_ratio")
        metrics.revenue_ttm = snapshot.get("revenue_ttm")

        # 计算同比营收增速（需要前期数据）
        if prev_snapshot and prev_snapshot.get("revenue_ttm") and metrics.revenue_ttm:
            prev_rev = prev_snapshot["revenue_ttm"]
            if prev_rev != 0:
                metrics.revenue_growth_yoy = round(
                    (metrics.revenue_ttm - prev_rev) / abs(prev_rev) * 100, 1
                )

        # 风险信号检测
        metrics.risk_signals = self._detect_risk_signals(metrics)

        return metrics

    def _detect_risk_signals(self, metrics: FinancialMetrics) -> list[str]:
        """
        检测财务风险信号。

        TODO: 扩展更多规则（如大股东减持、质押比例过高等）
        """
        signals: list[str] = []

        # PE 过高
        if metrics.pe_ratio and metrics.pe_ratio > 100:
            signals.append(f"⚠️ PE 过高（{metrics.pe_ratio:.1f}x），估值泡沫风险")

        # 营收增速骤降
        if metrics.revenue_growth_yoy is not None and metrics.revenue_growth_yoy < -10:
            signals.append(f"⚠️ 营收同比下降 {abs(metrics.revenue_growth_yoy):.1f}%")

        # 单日暴跌
        if metrics.change_pct_1d is not None and metrics.change_pct_1d < -5:
            signals.append(f"🔴 今日下跌 {abs(metrics.change_pct_1d):.1f}%，关注异常原因")

        return signals

    def format_for_report(self, metrics: FinancialMetrics) -> dict[str, Any]:
        """
        将财务指标格式化为报告所需的字典结构。

        TODO: 添加 MoM（环比）变化标注
        """
        return {
            "ticker": metrics.ticker,
            "price": metrics.price,
            "market_cap_bn": round(metrics.market_cap / 1e9, 2) if metrics.market_cap else None,
            "change_pct_1d": metrics.change_pct_1d,
            "pe_ratio": metrics.pe_ratio,
            "ps_ratio": metrics.ps_ratio,
            "revenue_ttm_mn": round(metrics.revenue_ttm / 1e6, 1) if metrics.revenue_ttm else None,
            "revenue_growth_yoy": metrics.revenue_growth_yoy,
            "risk_signals": metrics.risk_signals,
        }
