"""
src/analysis/competitor.py — 竞对对比分析模块

对比汇量科技（1860.HK）与主要竞对：
  - AppLovin (APP)
  - Unity Technologies (U)
  - Digital Turbine (APPS)

从市值、PE、营收增速等维度计算相对估值，
生成竞对对比表格和差异信号。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class CompetitorComparison:
    """单个竞对的对比数据。"""

    ticker: str
    price: float | None
    market_cap_bn: float | None  # 市值（十亿美元）
    change_pct_1d: float | None
    pe_ratio: float | None
    ps_ratio: float | None
    revenue_ttm_mn: float | None  # TTM 营收（百万美元）


class CompetitorAnalyzer:
    """
    竞对对比分析器。

    输入：最新 CompetitorSnapshot 记录列表
    输出：排名表格、差异信号、相对估值分析
    """

    def __init__(self) -> None:
        pass

    def build_comparison_table(
        self,
        snapshots: list[dict[str, Any]],
    ) -> list[CompetitorComparison]:
        """
        将快照列表转换为对比数据结构。

        Args:
            snapshots: CompetitorSnapshot 字典列表

        Returns:
            CompetitorComparison 列表，按市值降序排列

        TODO: 添加 52 周高低价、YTD 涨跌幅对比
        """
        comparisons: list[CompetitorComparison] = []
        for snap in snapshots:
            comparisons.append(
                CompetitorComparison(
                    ticker=snap.get("ticker", ""),
                    price=snap.get("price"),
                    market_cap_bn=round(snap["market_cap"] / 1e9, 2)
                    if snap.get("market_cap")
                    else None,
                    change_pct_1d=snap.get("change_pct"),
                    pe_ratio=snap.get("pe_ratio"),
                    ps_ratio=snap.get("ps_ratio"),
                    revenue_ttm_mn=round(snap["revenue_ttm"] / 1e6, 1)
                    if snap.get("revenue_ttm")
                    else None,
                )
            )
        # 按市值降序
        comparisons.sort(
            key=lambda c: c.market_cap_bn or 0,
            reverse=True,
        )
        return comparisons

    def find_divergence_signals(
        self,
        primary: CompetitorComparison,
        peers: list[CompetitorComparison],
    ) -> list[str]:
        """
        识别主标的与竞对之间的背离信号。

        Args:
            primary: 汇量科技的对比数据
            peers:   竞对的对比数据列表

        Returns:
            背离信号描述列表

        TODO: 实现更复杂的统计背离检测（如 Z-score）
        """
        signals: list[str] = []

        if not peers:
            return signals

        # 计算竞对平均涨跌幅
        peer_changes = [p.change_pct_1d for p in peers if p.change_pct_1d is not None]
        if peer_changes and primary.change_pct_1d is not None:
            peer_avg = sum(peer_changes) / len(peer_changes)
            diff = primary.change_pct_1d - peer_avg
            if diff < -3:
                signals.append(
                    f"📉 汇量今日涨跌 {primary.change_pct_1d:+.1f}%，"
                    f"竞对均值 {peer_avg:+.1f}%，背离 {diff:.1f}%"
                )
            elif diff > 3:
                signals.append(
                    f"📈 汇量今日涨跌 {primary.change_pct_1d:+.1f}%，"
                    f"竞对均值 {peer_avg:+.1f}%，超额表现 +{diff:.1f}%"
                )

        # PS 估值对比
        peer_ps = [p.ps_ratio for p in peers if p.ps_ratio is not None and p.ps_ratio > 0]
        if peer_ps and primary.ps_ratio:
            peer_ps_avg = sum(peer_ps) / len(peer_ps)
            discount = (primary.ps_ratio - peer_ps_avg) / peer_ps_avg * 100
            if discount < -30:
                signals.append(
                    f"💡 汇量 PS {primary.ps_ratio:.1f}x，竞对均值 {peer_ps_avg:.1f}x，"
                    f"折价 {abs(discount):.0f}%，存在价值洼地"
                )

        return signals

    def format_table_rows(
        self,
        comparisons: list[CompetitorComparison],
    ) -> list[dict[str, Any]]:
        """
        将对比数据格式化为飞书卡片表格行。

        Returns:
            表格行字典列表

        TODO: 添加颜色标记（涨跌幅红绿色）
        """
        rows = []
        primary_ticker = settings.primary_ticker
        for c in comparisons:
            rows.append(
                {
                    "ticker": f"{'⭐ ' if c.ticker == primary_ticker else ''}{c.ticker}",
                    "price": f"{c.price:.2f}" if c.price else "N/A",
                    "change": f"{c.change_pct_1d:+.1f}%" if c.change_pct_1d is not None else "N/A",
                    "market_cap": f"${c.market_cap_bn:.1f}B" if c.market_cap_bn else "N/A",
                    "pe": f"{c.pe_ratio:.1f}x" if c.pe_ratio else "N/A",
                    "ps": f"{c.ps_ratio:.1f}x" if c.ps_ratio else "N/A",
                    "revenue": f"${c.revenue_ttm_mn:.0f}M" if c.revenue_ttm_mn else "N/A",
                }
            )
        return rows
