"""
src/collectors/base.py — 数据采集器抽象基类

无状态设计：每次采集通过 since 参数控制时间窗口，
不依赖 Redis 或数据库来记录游标。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class CollectorError(Exception):
    """采集器运行时异常基类。"""

    pass


class BaseCollector(ABC):
    """
    数据采集器抽象基类。

    子类必须实现：
      - collect(since)  — 执行采集逻辑，返回采集结果列表
      - platform        — 字符串属性，标识数据来源

    无状态：不依赖 Redis/数据库，通过 since 参数避免重复分析历史数据。
    """

    platform: str = "base"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def collect(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """
        执行一次数据采集，返回原始数据列表。

        Args:
            since: 只返回该时间点之后发布的数据。
                   定时任务传入当天 00:00 HKT，仅采集今日评论。
                   为 None 时不做时间过滤（全量）。

        每条记录至少包含：
          - platform (str)      数据来源
          - ticker   (str)      关联标的
          - content  (str)      文本内容
          - captured_at (str)   发布时间 ISO 8601

        Returns:
            符合条件的数据列表，无数据则返回空列表。
        """
        ...

    async def run_once(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """
        安全执行一次采集，捕获并记录异常。

        Args:
            since: 透传给 collect()，只采集该时间点之后的数据。
        """
        try:
            results = await self.collect(since=since)
            self.logger.info(
                "[%s] 采集完成，%d 条（since=%s）",
                self.platform,
                len(results),
                since.isoformat() if since else "全量",
            )
            return results
        except CollectorError as e:
            self.logger.error("[%s] 采集失败: %s", self.platform, e)
            return []
        except Exception as e:
            self.logger.exception("[%s] 未知错误: %s", self.platform, e)
            return []

    # 别名
    safe_collect = run_once

    async def close(self) -> None:
        """释放资源（子类按需覆盖）。"""
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} platform={self.platform}>"
