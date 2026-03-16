"""
src/collectors/hkex.py — 港交所披露易公告采集器

轮询港交所披露易（HKEXnews）API，获取汇量科技（股票代码 01860）
的最新公告，自动识别公告类型并打优先级。

API 端点（非官方，可能变更）：
    https://www1.hkexnews.hk/listedco/listconews/advancedsearch/search_active_main.aspx
    JSON API: https://www1.hkexnews.hk/listedco/listconews/advancedsearch/json/...

注意：港交所无公开官方 API，此处使用反向工程的内部接口。
TODO: 如港交所开放官方 API，迁移至官方接口。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config.settings import settings
from src.collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)

# 港交所披露易公告搜索 API（内部接口，可能失效）
HKEX_API_URL = (
    "https://www1.hkexnews.hk/listedco/listconews/advancedsearch/json/"
    "GetAnnouncement.aspx"
)

# 公告类型关键词映射（优先级打标）
ANNOUNCEMENT_RULES: list[dict[str, Any]] = [
    {
        "keywords": ["业绩", "盈利警告", "中期业绩", "年度业绩", "Profit Warning", "Results"],
        "type": "earnings",
        "priority": 3,
    },
    {
        "keywords": ["回购", "购回", "Share Repurchase", "Buyback"],
        "type": "buyback",
        "priority": 2,
    },
    {
        "keywords": ["股权变动", "股东权益", "持股", "Shareholding", "Disclosure of Interest"],
        "type": "shareholding",
        "priority": 2,
    },
    {
        "keywords": ["派息", "股息", "Dividend", "Distribution"],
        "type": "dividend",
        "priority": 2,
    },
    {
        "keywords": ["董事", "行政总裁", "CEO", "CFO", "管理层变动", "Director", "Appointment"],
        "type": "management",
        "priority": 2,
    },
]

DEFAULT_TYPE = "general"
DEFAULT_PRIORITY = 1


def classify_announcement(title: str) -> tuple[str, int]:
    """
    根据公告标题文本识别类型并返回优先级。

    Args:
        title: 公告标题字符串（中英文均支持）

    Returns:
        (announcement_type, priority) 元组

    TODO: 引入 NLP 分类器提升准确率
    """
    title_lower = title.lower()
    for rule in ANNOUNCEMENT_RULES:
        if any(kw.lower() in title_lower for kw in rule["keywords"]):
            return rule["type"], rule["priority"]
    return DEFAULT_TYPE, DEFAULT_PRIORITY


class HKEXCollector(BaseCollector):
    """
    港交所披露易公告采集器。

    增量策略：记录最后一条公告的发布时间戳。
    """

    platform = "hkex"
    STOCK_CODE = "01860"  # 汇量科技港股代码

    async def _fetch_announcements(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        """
        通过港交所披露易接口获取公告列表。

        TODO: 实现真实的接口调用，当前为 mock 占位
        TODO: 处理分页（港交所每页最多 20 条）
        TODO: 添加 Retry-After 支持和指数退避
        """
        # TODO: 替换为真实 API 请求
        # 示例请求（需逆向工程实际参数）：
        # params = {
        #     "lang": "ZH",
        #     "stock_code": self.STOCK_CODE,
        #     "date_from": "",
        #     "date_to": "",
        #     "category": "0",
        # }
        # resp = await client.get(HKEX_API_URL, params=params)
        # data = resp.json()

        # ─── 临时 Mock 数据（待替换）───────────────────────────────────────
        logger.warning("HKEXCollector: 使用 Mock 数据，请实现真实 API 采集逻辑")
        return [
            {
                "id": "mock-001",
                "title": "汇量科技集团有限公司 — 2024年度业绩公告",
                "published_at": "2025-03-15T08:30:00+08:00",
                "url": f"https://www1.hkexnews.hk/listedco/listconews/{self.STOCK_CODE}/mock",
            },
            {
                "id": "mock-002",
                "title": "Purchase of Shares under Share Repurchase Mandate",
                "published_at": "2025-03-14T09:00:00+08:00",
                "url": f"https://www1.hkexnews.hk/listedco/listconews/{self.STOCK_CODE}/mock2",
            },
        ]

    async def collect(self) -> list[dict[str, Any]]:
        """
        执行一次港交所公告采集。

        Returns:
            新增公告列表（统一格式）。
        """
        last_id = await self.get_last_id()
        self.logger.info("HKEX 采集开始，last_id=%s", last_id)

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 StockBot/1.0"},
            follow_redirects=True,
        ) as client:
            raw_list = await self._fetch_announcements(client)

        results: list[dict[str, Any]] = []
        new_last_id: str | None = None

        for raw in raw_list:
            ann_id = raw.get("id", "")

            # 增量过滤（按 ID 或时间戳去重）
            if last_id and ann_id <= last_id:
                continue

            title = raw.get("title", "")
            ann_type, priority = classify_announcement(title)

            parsed: dict[str, Any] = {
                "platform": self.platform,
                "ticker": settings.primary_ticker,
                "external_id": ann_id,
                "title": title,
                "announcement_type": ann_type,
                "priority": priority,
                "url": raw.get("url", ""),
                "published_at": raw.get("published_at", datetime.now(timezone.utc).isoformat()),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
            results.append(parsed)

            if new_last_id is None:
                new_last_id = ann_id

        if new_last_id:
            await self.save_last_id(new_last_id)

        # 高优先级公告立即触发 alert
        high_priority = [r for r in results if r.get("priority", 1) >= 3]
        if high_priority:
            self.logger.warning(
                "发现 %d 条高优先级公告！%s",
                len(high_priority),
                [r["title"] for r in high_priority],
            )

        self.logger.info("HKEX 采集完成，新公告 %d 条", len(results))
        return results
