"""
src/collectors/base.py — 数据采集器抽象基类

所有采集器均继承 BaseCollector，实现统一的接口：
  - collect()        执行一次采集
  - get_last_id()    读取上次采集游标（用于增量采集）
  - save_last_id()   保存本次采集游标
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import redis.asyncio as aioredis

from config.settings import settings

logger = logging.getLogger(__name__)


class CollectorError(Exception):
    """采集器运行时异常基类。"""

    pass


class BaseCollector(ABC):
    """
    数据采集器抽象基类。

    子类必须实现：
      - collect()   — 执行采集逻辑，返回采集结果列表
      - platform    — 字符串属性，标识数据来源

    游标存储在 Redis，Key 格式：``collector:{platform}:last_id``
    """

    # 子类必须覆盖
    platform: str = "base"

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ── Redis 连接 ──────────────────────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        """懒初始化 Redis 连接。"""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    @property
    def _cursor_key(self) -> str:
        """Redis 游标键名。"""
        return f"collector:{self.platform}:last_id"

    # ── 游标管理 ────────────────────────────────────────────────────────────

    async def get_last_id(self) -> str | None:
        """
        读取上次成功采集的内容游标（如最新评论 ID、时间戳等）。

        Returns:
            上次游标字符串，如从未采集则返回 None。
        """
        redis = await self._get_redis()
        value = await redis.get(self._cursor_key)
        self.logger.debug("读取游标 %s = %s", self._cursor_key, value)
        return value

    async def save_last_id(self, last_id: str) -> None:
        """
        保存本次采集的游标，供下次增量采集使用。

        Args:
            last_id: 本次采集的最新内容游标。
        """
        redis = await self._get_redis()
        await redis.set(self._cursor_key, last_id)
        self.logger.debug("保存游标 %s = %s", self._cursor_key, last_id)

    # ── 核心采集接口 ─────────────────────────────────────────────────────────

    @abstractmethod
    async def collect(self) -> list[dict[str, Any]]:
        """
        执行一次数据采集，返回原始数据列表。

        每条记录是一个字典，至少包含以下字段：
          - platform (str)      数据来源平台
          - ticker   (str)      关联标的
          - content  (str)      文本内容
          - captured_at (str)   采集时间 ISO 8601

        Returns:
            采集到的原始数据列表。若无新数据则返回空列表。

        Raises:
            CollectorError: 采集过程中的已知错误。
        """
        ...

    async def run_once(self) -> list[dict[str, Any]]:
        """
        安全执行一次采集，捕获并记录异常。

        Returns:
            同 collect()，出错时返回空列表。
        """
        try:
            results = await self.collect()
            self.logger.info(
                "[%s] 采集完成，获得 %d 条记录", self.platform, len(results)
            )
            return results
        except CollectorError as e:
            self.logger.error("[%s] 采集失败: %s", self.platform, e)
            return []
        except Exception as e:
            self.logger.exception("[%s] 未知错误: %s", self.platform, e)
            return []

    async def close(self) -> None:
        """释放资源（Redis 连接等）。"""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} platform={self.platform}>"
