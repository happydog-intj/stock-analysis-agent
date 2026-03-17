"""
src/collectors/xueqiu.py — 雪球评论采集器

使用 Playwright 异步爬取 https://xueqiu.com/S/01860 的评论帖子，
支持增量采集（基于最新帖子 ID）。

依赖：
    playwright install chromium

注意：雪球需要登录 Cookie 才能访问部分内容，
可通过 XUEQIU_COOKIES 环境变量注入（JSON 格式）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timezone
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from config.settings import settings
from src.collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)

# 雪球汇量科技股票讨论页
XUEQIU_URL = "https://xueqiu.com/S/01860"

# 雪球 API：获取股票帖子列表（非官方，可能随版本变化）
XUEQIU_API_POSTS = (
    "https://xueqiu.com/query/v1/symbol/search/status.json?count=20&symbol=01860&type=11"
)


class XueqiuCollector(BaseCollector):
    """
    雪球评论采集器（Playwright 异步爬虫）。

    增量策略：记录最新帖子 ID，下次采集时跳过已处理记录。
    """

    platform = "xueqiu"

    def __init__(self) -> None:
        super().__init__()
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def _get_context(self) -> BrowserContext:
        """
        获取（或创建）Playwright 浏览器上下文。

        TODO: 支持注入 Cookie，解锁登录后内容
        TODO: 添加 User-Agent 伪装与 Stealth 插件
        """
        if self._context is None:
            # TODO: 考虑使用持久化上下文保存 Session
            playwright = await async_playwright().start()
            self._browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            # 注入 XUEQIU_COOKIES（支持 JSON 列表或 key=value; 字符串两种格式）
            raw_cookies = settings.xueqiu_cookies.strip()
            if raw_cookies:
                try:
                    cookie_list = json.loads(raw_cookies)
                    if isinstance(cookie_list, list):
                        # Playwright cookie 格式：补充必要字段
                        pw_cookies = [
                            {
                                "name": c.get("name", c.get("key", "")),
                                "value": c.get("value", ""),
                                "domain": c.get("domain", ".xueqiu.com"),
                                "path": c.get("path", "/"),
                            }
                            for c in cookie_list
                            if c.get("name") or c.get("key")
                        ]
                    else:
                        pw_cookies = []
                except json.JSONDecodeError:
                    # 纯字符串格式：key=value; key2=value2
                    pw_cookies = [
                        {
                            "name": part.split("=", 1)[0].strip(),
                            "value": part.split("=", 1)[1].strip() if "=" in part else "",
                            "domain": ".xueqiu.com",
                            "path": "/",
                        }
                        for part in raw_cookies.split(";")
                        if "=" in part.strip()
                    ]
                if pw_cookies:
                    await self._context.add_cookies(pw_cookies)
                    self.logger.info("已注入 %d 条雪球 Cookie", len(pw_cookies))
                else:
                    self.logger.warning("XUEQIU_COOKIES 解析结果为空，将以未登录状态访问")
        return self._context

    async def _fetch_posts_via_api(self, page: Page) -> list[dict[str, Any]]:
        """
        通过雪球内部 API 接口获取帖子列表。

        TODO: 处理分页，支持 max_id 翻页参数
        TODO: 处理 429 限速，添加退避重试
        """
        try:
            response = await page.goto(XUEQIU_API_POSTS, wait_until="networkidle")
            if response is None or response.status != 200:
                raise CollectorError(f"雪球 API 请求失败，状态码: {response and response.status}")
            text = await page.inner_text("body")
            data = json.loads(text)
            return data.get("list", [])
        except json.JSONDecodeError as e:
            raise CollectorError(f"解析雪球 API 响应失败: {e}") from e

    async def _parse_post(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """
        解析单条雪球帖子原始数据为统一格式。

        TODO: 提取更多字段（转发数、点赞数、回复数）
        TODO: 过滤广告帖子
        """
        try:
            post_id = str(raw.get("id", ""))
            content = raw.get("text", "") or raw.get("description", "")
            # 去除 HTML 标签（简单处理）
            # TODO: 使用 BeautifulSoup 或正则更精确地清理 HTML
            import re

            content = re.sub(r"<[^>]+>", "", content).strip()

            created_ms = raw.get("created_at", 0)
            created_at = datetime.fromtimestamp(created_ms / 1000, tz=UTC).isoformat()

            return {
                "platform": self.platform,
                "ticker": settings.primary_ticker,
                "external_id": post_id,
                "content": content[:2000],  # 截断超长内容
                "author": raw.get("user", {}).get("screen_name", ""),
                "captured_at": created_at,
                "raw": raw,  # 保留原始数据供调试
            }
        except Exception as e:
            self.logger.warning("解析帖子失败: %s", e)
            return None

    async def collect(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """
        执行一次雪球评论采集。

        Args:
            since: 只返回该时间点之后发布的帖子。
                   定时任务传入当天 00:00 HKT，仅采集今日评论。
                   帖子按时间倒序排列，遇到早于 since 的即提前终止。
        """
        self.logger.info("雪球采集开始，since=%s", since.isoformat() if since else "全量")

        context = await self._get_context()
        page = await context.new_page()

        try:
            raw_posts = await self._fetch_posts_via_api(page)
        finally:
            await page.close()

        if not raw_posts:
            self.logger.info("雪球：未获取到帖子")
            return []

        results: list[dict[str, Any]] = []
        since_aware = since.replace(tzinfo=UTC) if since and since.tzinfo is None else since

        for raw in raw_posts:
            parsed = await self._parse_post(raw)
            if not parsed:
                continue

            # 时间窗口过滤：帖子倒序，遇到早于 since 的直接终止
            if since_aware:
                try:
                    post_time = datetime.fromisoformat(parsed["captured_at"])
                    if post_time.tzinfo is None:
                        post_time = post_time.replace(tzinfo=UTC)
                    if post_time < since_aware:
                        self.logger.debug("帖子早于 since，终止遍历")
                        break
                except (KeyError, ValueError) as e:
                    self.logger.warning("解析帖子时间失败，跳过: %s", e)
                    continue

            results.append(parsed)

        self.logger.info("雪球采集完成，%d 条", len(results))
        return results

    async def close(self) -> None:
        """关闭浏览器并释放 Redis 连接。"""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        await super().close()
