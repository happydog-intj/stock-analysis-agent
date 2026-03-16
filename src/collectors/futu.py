"""
src/collectors/futu.py — 富途证券数据采集器

通过富途 FutuOpenD 本地服务（futu-api）获取港股实时行情、
资金流向、大单明细等数据。

前置条件：
  - 本地安装并运行 FutuOpenD（https://openapi.futunn.com/）
  - 配置 FUTU_HOST 和 FUTU_PORT（默认 127.0.0.1:11111）

依赖：
    pip install futu-api

TODO: 完整实现（当前为骨架，待实现具体采集逻辑）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from src.collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)


class FutuCollector(BaseCollector):
    """
    富途 OpenAPI 数据采集器。

    主要采集内容：
      - 实时报价（Bid/Ask/Last）
      - 资金流向（北向资金 / 散户净流入）
      - Level 2 大单明细
      - 打新 / 配售信息
    """

    platform = "futu"

    def __init__(self) -> None:
        super().__init__()
        # TODO: 初始化 futu.SysConfig 和 OpenQuoteContext
        self._quote_ctx: Any = None

    async def _connect(self) -> None:
        """
        连接 FutuOpenD 服务。

        TODO: 使用 futu.OpenQuoteContext(host, port) 建立连接
        TODO: 处理连接失败的重试逻辑
        """
        # import futu
        # futu.SysConfig.set_init_rsa_file("futu_rsa.pem")  # 如需加密
        # self._quote_ctx = futu.OpenQuoteContext(
        #     host=settings.futu_host, port=settings.futu_port
        # )
        logger.warning("FutuCollector: 连接逻辑待实现 (TODO)")

    async def collect(self) -> list[dict[str, Any]]:
        """
        采集富途行情与资金流向数据。

        TODO: 实现以下采集逻辑：
          1. 调用 quote_ctx.get_market_snapshot(['HK.01860']) 获取快照
          2. 调用 quote_ctx.get_capital_flow('HK.01860') 获取资金流向
          3. 调用 quote_ctx.get_order_book('HK.01860') 获取盘口
          4. 将数据转换为统一格式并返回

        Returns:
            行情快照列表（当前返回空列表）
        """
        logger.info("FutuCollector.collect() 待实现")
        # TODO: 实现真实采集逻辑
        return []

    async def close(self) -> None:
        """关闭 FutuOpenD 连接。"""
        # TODO: if self._quote_ctx: self._quote_ctx.close()
        await super().close()
