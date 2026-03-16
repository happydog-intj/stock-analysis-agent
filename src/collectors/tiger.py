"""
src/collectors/tiger.py — Tiger Broker 数据采集器

通过 Tiger Open API（老虎证券）获取港美股行情数据。

前置条件：
  - 申请 Tiger Open API 权限（https://quant.tigerfintech.com/）
  - 配置 TIGER_TIGER_ID 和 TIGER_PRIVATE_KEY

依赖：
    pip install tigeropen

TODO: 完整实现（当前为骨架，待实现具体采集逻辑）
"""

from __future__ import annotations

import logging
from typing import Any

from src.collectors.base import BaseCollector
from config.settings import settings

logger = logging.getLogger(__name__)


class TigerCollector(BaseCollector):
    """
    Tiger Broker OpenAPI 数据采集器。

    主要采集内容：
      - 实时报价
      - 历史 K 线数据（作为 Yahoo Finance 的补充/备用）
      - 经纪商资讯与研报摘要
    """

    platform = "tiger"

    def __init__(self) -> None:
        super().__init__()
        # TODO: 初始化 TigerOpenConfig 和 QuoteClient
        self._client: Any = None

    async def _get_client(self) -> Any:
        """
        懒初始化 Tiger Open API 客户端。

        TODO: 实现以下初始化逻辑：
            from tigeropen.tiger_open_config import TigerOpenConfig
            from tigeropen.quote.quote_client import QuoteClient
            config = TigerOpenConfig()
            config.private_key = settings.tiger_private_key
            config.tiger_id = settings.tiger_tiger_id
            self._client = QuoteClient(config)
        """
        logger.warning("TigerCollector: 客户端初始化逻辑待实现 (TODO)")
        return None

    async def collect(self) -> list[dict[str, Any]]:
        """
        采集 Tiger Broker 行情数据。

        TODO: 实现以下采集逻辑：
          1. client.get_timeline(symbols=['01860'], period='1D') 获取分时
          2. client.get_bars(symbols=['01860'], period='day', limit=5) 获取 K 线
          3. 将数据转换为统一格式

        Returns:
            行情数据列表（当前返回空列表）
        """
        logger.info("TigerCollector.collect() 待实现")
        # TODO: 实现真实采集逻辑
        return []

    async def close(self) -> None:
        """关闭 Tiger API 连接。"""
        # TODO: if self._client: self._client.disconnect()
        await super().close()
