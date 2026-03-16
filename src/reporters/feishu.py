"""
飞书 Webhook 推送：将报告以富文本卡片形式推送到飞书群。
"""
from __future__ import annotations

import logging

import httpx

from config.settings import settings
from src.reporters.templates import ReportContext, render_morning, render_noon, render_close

logger = logging.getLogger(__name__)


class FeishuReporter:
    """飞书消息推送器（Webhook 卡片）。"""

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook = webhook_url or settings.FEISHU_WEBHOOK

    async def send_text(self, text: str) -> bool:
        """发送纯文本消息。"""
        payload = {"msg_type": "text", "content": {"text": text}}
        return await self._post(payload)

    async def send_card(self, title: str, content: str, color: str = "blue") -> bool:
        """发送富文本卡片。"""
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color,
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": self._to_lark_md(content),
                        },
                    },
                    {
                        "tag": "hr",
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": "由 StockAnalysisAgent 自动生成 · 仅供参考，不构成投资建议",
                            }
                        ],
                    },
                ],
            },
        }
        return await self._post(payload)

    async def send_morning_report(self, ctx: ReportContext) -> bool:
        text = render_morning(ctx)
        return await self.send_card(
            title=f"📊 汇量科技 {ctx.ticker} 晨报",
            content=text,
            color="blue",
        )

    async def send_noon_report(self, ctx: ReportContext) -> bool:
        text = render_noon(ctx)
        return await self.send_card(
            title=f"📊 汇量科技 {ctx.ticker} 午报",
            content=text,
            color="wathet",
        )

    async def send_close_report(self, ctx: ReportContext) -> bool:
        text = render_close(ctx)
        # 根据情绪分决定卡片颜色
        color = "green" if ctx.sentiment_score >= 20 else "red" if ctx.sentiment_score <= -20 else "grey"
        return await self.send_card(
            title=f"📊 汇量科技 {ctx.ticker} 收盘报",
            content=text,
            color=color,
        )

    async def send_urgent_alert(self, title: str, detail: str) -> bool:
        """高优先级预警（红色卡片）。"""
        return await self.send_card(title=f"🚨 {title}", content=detail, color="red")

    async def _post(self, payload: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._webhook, json=payload)
                resp.raise_for_status()
                result = resp.json()
                if result.get("code", 0) != 0:
                    logger.error("飞书推送失败: %s", result)
                    return False
                logger.info("飞书推送成功")
                return True
        except Exception as e:
            logger.error("飞书推送异常: %s", e, exc_info=True)
            return False

    @staticmethod
    def _to_lark_md(text: str) -> str:
        """将纯文本转为飞书 lark_md 格式（简单适配）。"""
        lines = []
        for line in text.splitlines():
            if line.startswith("##"):
                lines.append(f"**{line.lstrip('#').strip()}**")
            else:
                lines.append(line)
        return "\n".join(lines)
