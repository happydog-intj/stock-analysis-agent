"""
雪球评论采集器：使用 Playwright 异步爬取 1860.HK 股票讨论区。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import redis.asyncio as aioredis
from playwright.async_api import async_playwright, Browser, Page

from config.settings import settings
from src.collectors.base import BaseCollector, RawComment

logger = logging.getLogger(__name__)


class XueqiuCollector(BaseCollector):
    """雪球平台评论采集器。"""

    platform = "xueqiu"
    STOCK_URL = "https://xueqiu.com/S/{symbol}"
    API_URL   = (
        "https://stock.xueqiu.com/v5/stock/tweet/list.json"
        "?symbol={symbol}&count=20&source=user"
    )

    def __init__(self, ticker: str = "01860") -> None:
        super().__init__(ticker=ticker)
        self._redis: aioredis.Redis | None = None
        self._symbol = f"HK{ticker.zfill(5)}"   # → HK01860

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def get_last_id(self) -> str | None:
        r = await self._get_redis()
        return await r.get(f"collector:xueqiu:{self.ticker}:last_id")

    async def save_last_id(self, last_id: str) -> None:
        r = await self._get_redis()
        await r.set(f"collector:xueqiu:{self.ticker}:last_id", last_id)

    async def collect(self) -> list[RawComment]:
        """主采集入口：Playwright 登录 + API 拉取评论。"""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
            )

            # 注入 cookie（避免重复登录，cookie 从 settings 读取）
            if settings.XUEQIU_COOKIES:
                cookies = json.loads(settings.XUEQIU_COOKIES)
                await context.add_cookies(cookies)

            page = await context.new_page()
            comments = await self._fetch_comments(page)
            await browser.close()

        return comments

    async def _fetch_comments(self, page: Page) -> list[RawComment]:
        """通过页面 API 接口拉取评论列表。"""
        # 先访问股票页面，让 cookie 生效
        url = self.STOCK_URL.format(symbol=self._symbol)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)

        last_id = await self.get_last_id()
        comments: list[RawComment] = []

        api_url = self.API_URL.format(symbol=self._symbol)
        response = await page.evaluate(
            f"""async () => {{
                const r = await fetch('{api_url}', {{credentials: 'include'}});
                return await r.json();
            }}"""
        )

        items = response.get("data", {}).get("list", [])
        new_last_id = None

        for item in items:
            tweet_id = str(item.get("id", ""))
            if last_id and tweet_id <= last_id:
                break   # 已采集过

            if new_last_id is None:
                new_last_id = tweet_id

            text: str = item.get("text", "")
            # 去除 HTML 标签
            text = self._strip_html(text)
            if not text.strip():
                continue

            created_ms = item.get("created_at", 0)
            published_at = datetime.fromtimestamp(created_ms / 1000) if created_ms else datetime.utcnow()

            user = item.get("user", {})
            comments.append(RawComment(
                platform=self.platform,
                ticker=self.ticker,
                content=text,
                author_id=str(user.get("id", "")),
                author_followers=user.get("followers_count", 0),
                likes=item.get("like_count", 0),
                published_at=published_at,
                raw=item,
            ))

        if new_last_id:
            await self.save_last_id(new_last_id)

        logger.info("雪球采集完成：新增 %d 条评论", len(comments))
        return comments

    @staticmethod
    def _strip_html(text: str) -> str:
        """简单去除 HTML 标签。"""
        import re
        return re.sub(r"<[^>]+>", "", text).strip()
