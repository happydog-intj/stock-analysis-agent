"""
src/reporters/feishu.py — 飞书 Webhook 推送器

通过飞书机器人 Webhook 发送富文本卡片消息。

支持：
  - 定时报告（晨报/午报/收盘报）
  - 即时告警（高优先级公告/股价暴跌/情绪骤变）
  - 签名校验（可选，通过 FEISHU_SECRET 配置）

飞书 Webhook 文档：
  https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN

TODO: 支持飞书 Bot API（@用户、指定频道）而非仅 Webhook
TODO: 失败时写入死信队列，支持重试
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

from config.settings import settings
from src.reporters.base import BaseReporter
from src.reporters.templates import TEMPLATE_BUILDERS

logger = logging.getLogger(__name__)

# 告警级别对应的飞书卡片颜色
ALERT_COLORS = {
    "low": "blue",
    "medium": "yellow",
    "high": "red",
}


class FeishuReporter(BaseReporter):
    """
    飞书 Webhook 报告推送器。

    每次调用 send_report 或 send_alert 时创建新的 httpx 客户端，
    无需保持长连接。
    """

    def __init__(self) -> None:
        self.webhook_url = settings.feishu_webhook
        self.secret = settings.feishu_secret

    def _sign(self, timestamp: int) -> str:
        """
        生成飞书 Webhook 签名（HMAC-SHA256）。

        Args:
            timestamp: Unix 时间戳（秒）

        Returns:
            Base64 编码的签名字符串

        TODO: 验证签名格式与飞书文档一致
        """
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def _build_payload(self, card: dict[str, Any]) -> dict[str, Any]:
        """
        构建飞书消息 payload，可选附加签名。

        Args:
            card: 飞书消息卡片字典

        Returns:
            完整的请求 payload
        """
        payload: dict[str, Any] = {
            "msg_type": card.get("msg_type", "interactive"),
            "card": card.get("card", card),
        }

        # 如果配置了签名密钥，附加 timestamp + sign
        if self.secret:
            timestamp = int(time.time())
            payload["timestamp"] = str(timestamp)
            payload["sign"] = self._sign(timestamp)

        return payload

    async def _post(self, payload: dict[str, Any]) -> bool:
        """
        执行 HTTP POST 请求到飞书 Webhook。

        Args:
            payload: 完整请求体

        Returns:
            成功返回 True，失败返回 False

        TODO: 添加指数退避重试（最多 3 次）
        TODO: 记录推送结果到 DB（用于统计推送成功率）
        """
        if not self.webhook_url:
            logger.warning("FEISHU_WEBHOOK 未配置，跳过推送")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp_data = resp.json()

                if resp_data.get("code") == 0 or resp_data.get("StatusCode") == 0:
                    logger.info("飞书推送成功")
                    return True
                else:
                    logger.error(
                        "飞书推送失败: code=%s, msg=%s",
                        resp_data.get("code"),
                        resp_data.get("msg"),
                    )
                    return False

        except httpx.TimeoutException:
            logger.error("飞书推送超时")
            return False
        except Exception as e:
            logger.exception("飞书推送异常: %s", e)
            return False

    async def send_report(self, data: dict[str, Any]) -> bool:
        """
        推送定时报告（晨报/午报/收盘报）。

        Args:
            data: 包含 period 字段及报告数据的字典

        Returns:
            推送成功返回 True

        TODO: 支持多个 Webhook（推送到多个群组）
        """
        period = data.get("period", "morning")
        builder = TEMPLATE_BUILDERS.get(period)

        if not builder:
            logger.error("未知报告类型: %s", period)
            return False

        card = builder(data)
        payload = self._build_payload(card)

        logger.info("推送 %s 报告到飞书...", period)
        success = await self._post(payload)

        if success:
            logger.info("%s 报告推送成功", period)
        return success

    async def send_alert(self, message: str, level: str = "medium") -> bool:
        """
        推送即时告警卡片。

        Args:
            message: 告警消息文本（支持 Markdown）
            level:   告警级别 "low" / "medium" / "high"

        Returns:
            推送成功返回 True

        TODO: 根据 level 决定是否 @所有人
        """
        color = ALERT_COLORS.get(level, "yellow")
        level_emoji = {"low": "ℹ️", "medium": "⚠️", "high": "🚨"}.get(level, "⚠️")

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{level_emoji} 汇量科技 1860.HK 告警",
                    },
                    "template": color,
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": message,
                        },
                    }
                ],
            },
        }

        payload = self._build_payload(card)
        logger.warning("推送告警 [%s]: %s", level, message[:80])
        return await self._post(payload)

    async def send_text(self, text: str) -> bool:
        """
        推送简单文本消息（用于调试）。

        Args:
            text: 文本内容

        Returns:
            推送成功返回 True
        """
        payload: dict[str, Any] = {
            "msg_type": "text",
            "content": {"text": text},
        }
        if self.secret:
            timestamp = int(time.time())
            payload["timestamp"] = str(timestamp)
            payload["sign"] = self._sign(timestamp)
        return await self._post(payload)
