"""
src/agents/alert_agent.py — 风险预警 Agent

持续监控以下异常信号并立即推送飞书告警：
  - 高优先级港交所公告（业绩预警/监管函件）
  - 情绪急剧恶化（情绪分在 1 小时内骤降 >20 分）
  - 股价暴跌（>5% 单日跌幅）
  - 竞对重大事件（如 AppLovin 超预期财报）

与定时报告不同，Alert 是事件驱动的实时触发。
"""

from __future__ import annotations

import logging
from typing import Any

from src.reporters.feishu import FeishuReporter

logger = logging.getLogger(__name__)

# 触发告警的阈值
PRICE_DROP_THRESHOLD = -5.0       # 单日跌幅阈值（%）
SENTIMENT_DROP_THRESHOLD = -20.0  # 情绪骤降阈值（1h内）
MIN_ANNOUNCEMENT_PRIORITY = 3     # 公告优先级触发阈值


class AlertAgent:
    """
    风险预警 Agent。

    设计为轻量级：直接从 Orchestrator 传入数据，判断是否需要触发告警。
    """

    def __init__(self) -> None:
        self.reporter = FeishuReporter()

    async def check_and_alert(
        self,
        market_data: list[dict[str, Any]],
        announcements: list[dict[str, Any]],
        sentiment_summary: dict[str, Any] | None = None,
    ) -> list[str]:
        """
        检查所有预警条件，触发告警并返回已发送的告警列表。

        Args:
            market_data:       最新行情快照列表
            announcements:     最新公告列表
            sentiment_summary: 情绪汇总（含 current_avg 和 prev_avg）

        Returns:
            已触发的告警消息列表

        TODO: 添加告警去重（同一类型告警 1h 内不重复发送）
        TODO: 实现告警升级机制（持续异常 → 升级告警级别）
        """
        alerts: list[str] = []

        # ── 检查股价暴跌 ────────────────────────────────────────────────────
        for data in market_data:
            ticker = data.get("ticker", "")
            change_pct = data.get("change_pct")
            if change_pct is not None and change_pct <= PRICE_DROP_THRESHOLD:
                msg = (
                    f"🚨 价格预警：{ticker} 今日下跌 {change_pct:.1f}%，"
                    f"当前价 {data.get('price', 'N/A')}"
                )
                logger.warning(msg)
                await self.reporter.send_alert(msg, level="high")
                alerts.append(msg)

        # ── 检查高优先级公告 ─────────────────────────────────────────────────
        for ann in announcements:
            priority = ann.get("priority", 1)
            if priority >= MIN_ANNOUNCEMENT_PRIORITY:
                msg = (
                    f"📢 重要公告：{ann.get('title', '未知')} "
                    f"[优先级: P{priority}]"
                )
                logger.warning(msg)
                await self.reporter.send_alert(msg, level="high")
                alerts.append(msg)

        # ── 检查情绪骤降 ─────────────────────────────────────────────────────
        if sentiment_summary:
            current = sentiment_summary.get("current_avg")
            previous = sentiment_summary.get("prev_avg")
            if current is not None and previous is not None:
                drop = current - previous
                if drop <= SENTIMENT_DROP_THRESHOLD:
                    msg = (
                        f"😰 情绪预警：情绪分骤降 {drop:.1f}（"
                        f"从 {previous:.1f} → {current:.1f}）"
                    )
                    logger.warning(msg)
                    await self.reporter.send_alert(msg, level="medium")
                    alerts.append(msg)

        return alerts
