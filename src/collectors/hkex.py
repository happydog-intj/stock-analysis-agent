"""
港交所公告监听器：轮询 HKEX EPS，检测 1860 新公告并分类。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import httpx
import redis.asyncio as aioredis

from config.settings import settings

logger = logging.getLogger(__name__)

HKEX_SEARCH_URL = (
    "https://www1.hkexnews.hk/search/titlesearch.xhtml"
    "?lang=zh&category=0&market=MAINBOARD&searchType=1"
    "&documentNo=&stockCode={stock_code}&headline=&dateFrom=&dateTo="
    "&t1code=40000&t2Gcode=-2&t2code=-2&rowRange=20&btnSearch.x=48&btnSearch.y=10"
)


class AnnouncementPriority(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class AnnouncementType(str, Enum):
    PROFIT_WARNING  = "profit_warning"
    RESULTS         = "results"
    SHAREHOLDING    = "shareholding"
    MANAGEMENT      = "management"
    GENERAL         = "general"


CLASSIFICATION_RULES: list[tuple[list[str], AnnouncementType, AnnouncementPriority]] = [
    (["盈利警告", "正面盈利", "profit warning"],   AnnouncementType.PROFIT_WARNING,  AnnouncementPriority.HIGH),
    (["中期业绩", "全年业绩", "interim results", "annual results"],
                                                    AnnouncementType.RESULTS,         AnnouncementPriority.MEDIUM),
    (["主要股东", "股权", "持股", "major shareholder"],
                                                    AnnouncementType.SHAREHOLDING,    AnnouncementPriority.HIGH),
    (["董事", "行政总裁", "chief executive", "director"],
                                                    AnnouncementType.MANAGEMENT,      AnnouncementPriority.MEDIUM),
]


@dataclass
class HKEXAnnouncement:
    ticker:       str
    title:        str
    type:         AnnouncementType
    priority:     AnnouncementPriority
    url:          str
    published_at: datetime
    doc_id:       str


class HKEXCollector:
    """港交所公告监听器。"""

    STOCK_CODE = "1860"

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def _get_seen_ids(self) -> set[str]:
        r = await self._get_redis()
        members = await r.smembers(f"hkex:seen:{self.STOCK_CODE}")
        return set(members)

    async def _mark_seen(self, doc_id: str) -> None:
        r = await self._get_redis()
        await r.sadd(f"hkex:seen:{self.STOCK_CODE}", doc_id)
        await r.expire(f"hkex:seen:{self.STOCK_CODE}", 86400 * 30)  # 30 天

    def _classify(self, title: str) -> tuple[AnnouncementType, AnnouncementPriority]:
        title_lower = title.lower()
        for keywords, ann_type, priority in CLASSIFICATION_RULES:
            if any(kw.lower() in title_lower for kw in keywords):
                return ann_type, priority
        return AnnouncementType.GENERAL, AnnouncementPriority.LOW

    async def poll(self) -> list[HKEXAnnouncement]:
        """拉取最新公告，返回未见过的新公告。"""
        seen_ids = await self._get_seen_ids()
        new_announcements: list[HKEXAnnouncement] = []

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                url = HKEX_SEARCH_URL.format(stock_code=self.STOCK_CODE)
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                items = self._parse_response(resp.text)

            for item in items:
                if item["doc_id"] in seen_ids:
                    continue

                ann_type, priority = self._classify(item["title"])
                ann = HKEXAnnouncement(
                    ticker=self.STOCK_CODE,
                    title=item["title"],
                    type=ann_type,
                    priority=priority,
                    url=item["url"],
                    published_at=item["date"],
                    doc_id=item["doc_id"],
                )
                new_announcements.append(ann)
                await self._mark_seen(item["doc_id"])

        except Exception as e:
            logger.error("港交所公告拉取失败: %s", e, exc_info=True)

        if new_announcements:
            logger.info("港交所：发现 %d 条新公告", len(new_announcements))
        return new_announcements

    def _parse_response(self, html: str) -> list[dict]:
        """解析 HKEX 搜索结果页面（简单 HTML 解析）。"""
        from html.parser import HTMLParser
        import re

        results = []
        # 匹配公告条目（实际生产中应更健壮）
        pattern = re.compile(
            r'<td[^>]*class="[^"]*news-title[^"]*"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?'
            r'<td[^>]*class="[^"]*news-date[^"]*"[^>]*>([^<]+)</td>',
            re.DOTALL,
        )
        for m in pattern.finditer(html):
            href, title, date_str = m.group(1), m.group(2).strip(), m.group(3).strip()
            doc_id = href.split("/")[-1].replace(".pdf", "")
            try:
                date = datetime.strptime(date_str, "%d/%m/%Y")
            except ValueError:
                date = datetime.utcnow()

            results.append({
                "doc_id": doc_id,
                "title":  title,
                "url":    f"https://www1.hkexnews.hk{href}",
                "date":   date,
            })
        return results
