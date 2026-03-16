"""
src/reporters/base.py — 报告推送器抽象基类

所有推送器（飞书、邮件、Telegram 等）均继承此基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseReporter(ABC):
    """报告推送器基类。"""

    @abstractmethod
    async def send_report(self, data: dict[str, Any]) -> bool:
        """
        推送报告。

        Args:
            data: 报告数据字典

        Returns:
            推送成功返回 True，否则返回 False
        """
        ...

    @abstractmethod
    async def send_alert(self, message: str, level: str = "medium") -> bool:
        """
        推送即时告警。

        Args:
            message: 告警消息文本
            level:   告警级别 "low" / "medium" / "high"

        Returns:
            推送成功返回 True，否则返回 False
        """
        ...
