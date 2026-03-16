"""
报告文本模板：生成晨报、午报、收盘报的格式化文本。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _sentiment_bar(score: float, width: int = 10) -> str:
    """将情绪分数转为进度条字符串，score 范围 -100~100。"""
    normalized = (score + 100) / 200          # 0.0 ~ 1.0
    filled = round(normalized * width)
    return "█" * filled + "░" * (width - filled)


def _change_emoji(pct: float) -> str:
    if pct > 2:   return "🚀"
    if pct > 0:   return "📈"
    if pct < -2:  return "💥"
    if pct < 0:   return "📉"
    return "➡️"


@dataclass
class ReportContext:
    """报告所需数据上下文。"""
    ticker:          str
    price:           float
    prev_close:      float
    change_pct:      float
    volume:          int
    sentiment_score: float           # -100 ~ 100
    platform_scores: dict[str, float]  # {platform: score}
    top_topics:      list[dict]      # [{topic, count}]
    risk_signals:    list[str]
    competitor_table: str
    announcements:   list[str]        # 公告标题列表
    period:          str              # morning / noon / close
    timestamp:       datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now()


def render_morning(ctx: ReportContext) -> str:
    return _render(ctx, period_title="晨报（盘前）", include_competitor=True, include_outlook=True)


def render_noon(ctx: ReportContext) -> str:
    return _render(ctx, period_title="午报（盘中）", include_competitor=False, include_outlook=False)


def render_close(ctx: ReportContext) -> str:
    return _render(ctx, period_title="收盘报（盘后）", include_competitor=True, include_outlook=True)


def _render(
    ctx: ReportContext,
    period_title: str,
    include_competitor: bool,
    include_outlook: bool,
) -> str:
    ts = ctx.timestamp.strftime("%Y-%m-%d %H:%M") if ctx.timestamp else ""
    sign = "+" if ctx.change_pct >= 0 else ""
    emoji = _change_emoji(ctx.change_pct)

    # 情绪综合分
    sentiment_label = (
        "强势看多 🔥" if ctx.sentiment_score >= 60 else
        "偏多 📈"     if ctx.sentiment_score >= 20 else
        "中性 ➡️"     if ctx.sentiment_score >= -20 else
        "偏空 📉"     if ctx.sentiment_score >= -60 else
        "强势看空 ⚠️"
    )

    lines = [
        f"📊 汇量科技（{ctx.ticker}）{period_title}",
        f"⏰ {ts}",
        "",
        f"💹 最新价：HK${ctx.price:.2f}  {emoji} {sign}{ctx.change_pct:.1f}%",
        f"📦 成交量：{ctx.volume:,}",
        "",
        f"📣 情绪综合分：{ctx.sentiment_score:.0f}/100  {sentiment_label}",
    ]

    # 平台分项
    for platform, score in ctx.platform_scores.items():
        bar = _sentiment_bar(score, 8)
        lines.append(f"   {platform:<8} {bar} {score:.0f}")

    # 热点话题
    if ctx.top_topics:
        topics_str = " / ".join(
            f"{t['topic']}({t['count']})" for t in ctx.top_topics[:4]
        )
        lines.append("")
        lines.append(f"🔥 热点话题：{topics_str}")

    # 竞对对比
    if include_competitor and ctx.competitor_table:
        lines.append("")
        lines.append("🏆 竞对表现：")
        lines.append(ctx.competitor_table)

    # 公告
    lines.append("")
    if ctx.announcements:
        lines.append("📋 最新公告：")
        for ann in ctx.announcements[:3]:
            lines.append(f"   • {ann}")
    else:
        lines.append("📋 今日公告：暂无")

    # 风险信号
    if ctx.risk_signals:
        lines.append("")
        for sig in ctx.risk_signals:
            lines.append(f"⚠️  {sig}")

    # 展望
    if include_outlook:
        lines.append("")
        lines.append("📅 明日关注：无重要数据披露")

    return "\n".join(lines)
