"""
src/reporters/templates.py — 飞书卡片报告模板

定义三种报告模板（晨报/午报/收盘报）的飞书富文本卡片 JSON 结构。

飞书消息卡片文档：
  https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/im-v1/message/create_json

所有模板返回符合飞书 interactive 类型卡片规范的字典。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _sentiment_emoji(score: float | None) -> str:
    """根据情绪分返回对应 emoji。"""
    if score is None:
        return "😐"
    if score >= 60:
        return "🚀"
    if score >= 20:
        return "📈"
    if score >= -20:
        return "😐"
    if score >= -60:
        return "📉"
    return "💀"


def _change_pct_text(change: float | None) -> str:
    """格式化涨跌幅文本。"""
    if change is None:
        return "N/A"
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.2f}%"


def build_morning_report(data: dict[str, Any]) -> dict[str, Any]:
    """
    构建晨报飞书卡片。

    晨报内容：
      - 前日收盘价 & 涨跌幅
      - 隔夜海外竞对表现
      - 舆情情绪分（过去 16 小时）
      - 今日重要事项（公告/港股通流向）
      - 风险提示

    Args:
        data: Orchestrator 提供的报告数据字典

    Returns:
        飞书 interactive 消息卡片 JSON
    """
    financial = data.get("financial", {})
    snapshot = data.get("snapshot")
    announcements = data.get("announcements", [])
    divergence = data.get("divergence_signals", [])

    sentiment_avg = getattr(snapshot, "sentiment_avg", None) if snapshot else None
    price = financial.get("price")
    change = financial.get("change_pct_1d")
    market_cap = financial.get("market_cap_bn")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 公告摘要
    ann_text = "\n".join(
        f"• [{a.get('announcement_type', 'general').upper()}] {a.get('title', '')}"
        for a in announcements[:3]
    ) or "今日暂无重要公告"

    # 风险信号
    risk_items = (financial.get("risk_signals") or []) + divergence
    risk_text = "\n".join(risk_items) if risk_items else "✅ 暂无风险信号"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 晨报 | 汇量科技 1860.HK | {now_str}",
                },
                "template": "blue",
            },
            "elements": [
                # 行情概览
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**📌 行情概览**\n"
                            f"价格：**{price or 'N/A'} HKD** | "
                            f"涨跌：**{_change_pct_text(change)}** | "
                            f"市值：**{market_cap or 'N/A'}B USD**"
                        ),
                    },
                },
                {"tag": "hr"},
                # 情绪分
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**{_sentiment_emoji(sentiment_avg)} 舆情情绪**\n"
                            f"过去 16 小时情绪分：**{sentiment_avg:.1f}**"
                            if sentiment_avg is not None
                            else "**😐 舆情情绪**\n暂无足够数据"
                        ),
                    },
                },
                {"tag": "hr"},
                # 公告
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📢 今日公告**\n{ann_text}",
                    },
                },
                {"tag": "hr"},
                # 风险信号
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**⚠️ 风险信号**\n{risk_text}",
                    },
                },
            ],
        },
    }


def build_noon_report(data: dict[str, Any]) -> dict[str, Any]:
    """
    构建午报飞书卡片。

    午报内容：
      - 今日上午行情（成交量、资金流）
      - 上午舆情情绪变化
      - 竞对上午表现对比
      - 关键时间点提醒

    Args:
        data: Orchestrator 提供的报告数据字典

    Returns:
        飞书 interactive 消息卡片 JSON

    TODO: 添加分时情绪变化图（需要富文本图片支持）
    """
    financial = data.get("financial", {})
    snapshot = data.get("snapshot")
    competitor_table = data.get("competitor_table", [])

    sentiment_avg = getattr(snapshot, "sentiment_avg", None) if snapshot else None
    price = financial.get("price")
    change = financial.get("change_pct_1d")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 竞对表格文本
    table_lines = ["| 标的 | 价格 | 涨跌 | 市值 | PE |"]
    table_lines.append("|------|------|------|------|-----|")
    for row in competitor_table[:5]:
        table_lines.append(
            f"| {row.get('ticker')} | {row.get('price')} | "
            f"{row.get('change')} | {row.get('market_cap')} | {row.get('pe')} |"
        )
    table_text = "\n".join(table_lines) if competitor_table else "暂无竞对数据"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"☀️ 午报 | 汇量科技 1860.HK | {now_str}",
                },
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**📌 上午行情**\n"
                            f"当前价：**{price or 'N/A'} HKD** | "
                            f"今日涨跌：**{_change_pct_text(change)}**\n"
                            f"舆情情绪分：**{sentiment_avg:.1f if sentiment_avg else 'N/A'}**"
                            f" {_sentiment_emoji(sentiment_avg)}"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🏆 竞对对比**\n{table_text}",
                    },
                },
            ],
        },
    }


def build_close_report(data: dict[str, Any]) -> dict[str, Any]:
    """
    构建收盘报飞书卡片。

    收盘报内容（最完整版本）：
      - 今日收盘全天行情（OHLCV）
      - 全天舆情总结（情绪分 + Top 5 话题）
      - 竞对全天表现对比（完整表格）
      - 财务风险信号
      - 明日关注点

    Args:
        data: Orchestrator 提供的报告数据字典

    Returns:
        飞书 interactive 消息卡片 JSON

    TODO: 添加情绪趋势折线图（通过飞书图片消息）
    """
    financial = data.get("financial", {})
    snapshot = data.get("snapshot")
    competitor_table = data.get("competitor_table", [])
    divergence = data.get("divergence_signals", [])
    announcements = data.get("announcements", [])

    sentiment_avg = getattr(snapshot, "sentiment_avg", None) if snapshot else None
    top_topics = getattr(snapshot, "top_topics", None) if snapshot else None
    sample_count = getattr(snapshot, "sample_count", 0) if snapshot else 0
    price = financial.get("price")
    change = financial.get("change_pct_1d")
    market_cap = financial.get("market_cap_bn")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 话题列表
    topic_text = ""
    if top_topics:
        topic_lines = [
            f"• {t.get('topic', '')} ({t.get('count', 0)} 条)"
            for t in (top_topics[:5] if isinstance(top_topics, list) else [])
        ]
        topic_text = "\n".join(topic_lines) if topic_lines else "暂无热门话题"
    else:
        topic_text = "暂无话题数据"

    # 竞对表格
    table_lines = ["| 标的 | 价格 | 涨跌 | 市值 | PE | PS | 营收(TTM) |"]
    table_lines.append("|------|------|------|------|----|----|----|")
    for row in competitor_table:
        table_lines.append(
            f"| {row.get('ticker')} | {row.get('price')} | "
            f"{row.get('change')} | {row.get('market_cap')} | "
            f"{row.get('pe')} | {row.get('ps')} | {row.get('revenue')} |"
        )
    table_text = "\n".join(table_lines) if competitor_table else "暂无数据"

    # 风险信号
    risk_signals = financial.get("risk_signals", []) + divergence
    risk_text = "\n".join(risk_signals) if risk_signals else "✅ 今日无重大风险信号"

    # 重要公告
    ann_text = "\n".join(
        f"• [{a.get('priority', 1)}P] {a.get('title', '')}"
        for a in sorted(announcements, key=lambda x: x.get("priority", 1), reverse=True)[:3]
    ) or "今日无重要公告"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🔔 收盘报 | 汇量科技 1860.HK | {now_str}",
                },
                "template": "orange",
            },
            "elements": [
                # 收盘行情
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**📌 今日收盘**\n"
                            f"收盘价：**{price or 'N/A'} HKD** | "
                            f"涨跌：**{_change_pct_text(change)}** | "
                            f"市值：**{market_cap or 'N/A'}B USD**"
                        ),
                    },
                },
                {"tag": "hr"},
                # 全天情绪
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**{_sentiment_emoji(sentiment_avg)} 全天舆情汇总**\n"
                            f"情绪分：**{sentiment_avg:.1f}**（{sample_count} 条样本）\n\n"
                            f"**热门话题：**\n{topic_text}"
                            if sentiment_avg is not None
                            else "**😐 舆情数据不足**"
                        ),
                    },
                },
                {"tag": "hr"},
                # 竞对对比
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🏆 竞对全天表现**\n{table_text}",
                    },
                },
                {"tag": "hr"},
                # 公告
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📢 今日重要公告**\n{ann_text}",
                    },
                },
                {"tag": "hr"},
                # 风险信号
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**⚠️ 风险信号**\n{risk_text}",
                    },
                },
            ],
        },
    }


# 模板工厂字典
TEMPLATE_BUILDERS: dict[str, Any] = {
    "morning": build_morning_report,
    "noon": build_noon_report,
    "close": build_close_report,
}
