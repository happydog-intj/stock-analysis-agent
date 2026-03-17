"""
src/reporters/markdown.py — Markdown 报告生成器

生成供 GitHub Issue 使用的 Markdown 格式报告。
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any


def _pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _price(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "N/A"


def render_report(data: dict[str, Any]) -> str:
    """将报告数据渲染为 Markdown 字符串（用于 GitHub Issue）。"""
    period = data.get("period", "morning")
    period_label = {"morning": "晨报 🌅", "noon": "午报 ☀️", "close": "收盘报 🌙"}.get(
        period, period
    )
    snapshot: dict[str, Any] = data.get("snapshot") or {}
    announcements: list[dict] = data.get("announcements", [])
    competitor_table: list[Any] = data.get("competitor_table", [])
    financial: dict[str, Any] = data.get("financial") or {}
    divergence_signals: list[Any] = data.get("divergence_signals", [])
    sentiment_records: list[dict] = data.get("sentiment_records", [])

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        f"# 📊 汇量科技 1860.HK {period_label}",
        f"> 生成时间：{now}",
        "",
    ]

    # ── 主标的行情 ────────────────────────────────────────────
    price = snapshot.get("price")
    change = snapshot.get("change_pct")
    volume = snapshot.get("volume")
    sentiment_avg = snapshot.get("sentiment_avg")

    lines += [
        "## 📈 主标的行情",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 最新价 | {_price(price)} HKD |",
        f"| 涨跌幅 | {_pct(change)} |",
        f"| 成交量 | {int(volume):,} |" if volume else "| 成交量 | N/A |",
        f"| 舆情得分 | {sentiment_avg if sentiment_avg is not None else 'N/A'} |",
        "",
    ]

    # ── 竞对对比 ──────────────────────────────────────────────
    if competitor_table:
        lines.append("## 🏆 竞对对比")
        lines.append("| 标的 | 价格 | 涨跌幅 | 市值 |")
        lines.append("|------|------|--------|------|")
        for row in competitor_table:
            if hasattr(row, "ticker"):
                lines.append(
                    f"| {row.ticker} | {_price(getattr(row, 'price', None))} |"
                    f" {_pct(getattr(row, 'change_pct', None))} |"
                    f" {getattr(row, 'market_cap_fmt', 'N/A')} |"
                )
            elif isinstance(row, dict):
                lines.append(
                    f"| {row.get('ticker','?')} | {_price(row.get('price'))} |"
                    f" {_pct(row.get('change_pct'))} | {row.get('market_cap','N/A')} |"
                )
        lines.append("")

    # ── 分化信号 ──────────────────────────────────────────────
    if divergence_signals:
        lines.append("## ⚠️ 分化信号")
        for sig in divergence_signals:
            lines.append(f"- {sig}")
        lines.append("")

    # ── 港交所公告 ────────────────────────────────────────────
    if announcements:
        lines.append("## 📢 港交所公告")
        for ann in announcements:
            title = ann.get("title", "")
            url = ann.get("url", "")
            priority = ann.get("priority", 1)
            star = "🔴" if priority >= 3 else ("🟡" if priority == 2 else "⚪")
            link = f"[{title}]({url})" if url else title
            lines.append(f"- {star} {link}")
        lines.append("")

    # ── 财务指标 ──────────────────────────────────────────────
    if financial:
        lines.append("## 💰 财务指标")
        for k, v in financial.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    # ── 舆情摘要 ──────────────────────────────────────────────
    if sentiment_records:
        lines.append("## 💬 舆情样本（前 5 条）")
        for r in sentiment_records[:5]:
            platform = r.get("platform", "")
            content = (r.get("content") or "")[:120].replace("\n", " ")
            sentiment = r.get("sentiment", "")
            lines.append(f"- [{platform}] `{sentiment}` {content}…")
        lines.append("")

    lines.append("---")
    lines.append("*由 [stock-analysis-agent](https://github.com/happydog-intj/stock-analysis-agent) 自动生成*")

    return "\n".join(lines)
