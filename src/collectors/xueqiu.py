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
from datetime import datetime, timezone
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
    "https://xueqiu.com/query/v1/symbol/search/status.json"
    "?count=20&symbol=01860&type=11"
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
            # TODO: 从环境变量 XUEQIU_COOKIES 加载 Cookie
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
            created_at = datetime.fromtimestamp(
                created_ms / 1000, tz=timezone.utc
            ).isoformat()

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

        增量逻辑：
          1. 读取 Redis 中记录的 last_id（用于去重，防止同一帖子被重复分析）
          2. 采集最新帖子列表
          3. 过滤掉 id <= last_id 的已采集帖子（去重）
          4. 若指定 since，额外过滤发布时间早于 since 的帖子
          5. 保存最新帖子 id 为新游标

        Returns:
            符合条件的帖子列表（统一格式）。
        """
        last_id = await self.get_last_id()
        self.logger.info(
            "雪球采集开始，last_id=%s，since=%s",
            last_id,
            since.isoformat() if since else "不限",
        )

        context = await self._get_context()
        page = await context.new_page()

        try:
            # TODO: 优先尝试 API 接口，失败则降级到页面爬取
            raw_posts = await self._fetch_posts_via_api(page)
        finally:
            await page.close()

        if not raw_posts:
            self.logger.info("雪球：未获取到帖子")
            return []

        results: list[dict[str, Any]] = []
        new_last_id: str | None = None

        for raw in raw_posts:
            post_id = str(raw.get("id", ""))

            # ① 增量去重：跳过已采集帖子
            if last_id and post_id <= last_id:
                continue

            parsed = await self._parse_post(raw)
            if not parsed:
                continue

            # ② 日期窗口过滤：只保留 since 之后发布的帖子
            if since:
                try:
                    post_time = datetime.fromisoformat(parsed["captured_at"])
                    # 统一为 aware datetime 再比较
                    if post_time.tzinfo is None:
                        post_time = post_time.replace(tzinfo=timezone.utc)
                    since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                    if post_time < since_aware:
                        # 帖子按时间倒序，一旦遇到早于 since 的可以提前终止
                        self.logger.debug("帖子 %s 早于 since，停止遍历", post_id)
                        break
                except (KeyError, ValueError) as e:
                    self.logger.warning("解析帖子时间失败，跳过: %s", e)
                    continue

            results.append(parsed)
            # 记录最新 ID（假设帖子按时间倒序排列）
            if new_last_id is None:
                new_last_id = post_id

        if new_last_id:
            await self.save_last_id(new_last_id)

        self.logger.info(
            "雪球采集完成，今日新帖子 %d 条",
            len(results),
        )
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
