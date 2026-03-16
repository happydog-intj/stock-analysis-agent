"""
Reddit 评论采集器：使用 PRAW 监控相关子版块。
"""
from __future__ import annotations

import logging
from datetime import datetime

import praw
import redis.asyncio as aioredis

from config.settings import settings
from src.collectors.base import BaseCollector, RawComment

logger = logging.getLogger(__name__)

SUBREDDITS  = ["HKStocks", "stocks", "investing", "wallstreetbets"]
KEYWORDS    = ["Mobvista", "1860.HK", "Mintegral", "mobvista", "mintegral"]
SEARCH_DAYS = 1   # 只拉取最近 N 天内的帖子


class RedditCollector(BaseCollector):
    """Reddit 评论 & 帖子采集器。"""

    platform = "reddit"

    def __init__(self, ticker: str = "1860.HK") -> None:
        super().__init__(ticker=ticker)
        self._reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=f"StockAnalysisAgent/1.0 (ticker:{ticker})",
            username=settings.REDDIT_USERNAME,
            password=settings.REDDIT_PASSWORD,
        )
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def get_last_id(self) -> str | None:
        r = await self._get_redis()
        return await r.get(f"collector:reddit:{self.ticker}:last_id")

    async def save_last_id(self, last_id: str) -> None:
        r = await self._get_redis()
        await r.set(f"collector:reddit:{self.ticker}:last_id", last_id)

    async def collect(self) -> list[RawComment]:
        """搜索关键词，采集相关帖子 & 评论。"""
        # PRAW 是同步库，在异步上下文中用 run_in_executor
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_collect)

    def _sync_collect(self) -> list[RawComment]:
        comments: list[RawComment] = []
        seen_ids: set[str] = set()

        for subreddit_name in SUBREDDITS:
            subreddit = self._reddit.subreddit(subreddit_name)
            for keyword in KEYWORDS:
                try:
                    results = subreddit.search(
                        query=keyword,
                        sort="new",
                        time_filter="day",
                        limit=25,
                    )
                    for submission in results:
                        if submission.id in seen_ids:
                            continue
                        seen_ids.add(submission.id)

                        published = datetime.fromtimestamp(submission.created_utc)
                        # 帖子标题 + 正文
                        text = f"{submission.title}\n{submission.selftext}".strip()
                        if not text:
                            continue

                        comments.append(RawComment(
                            platform=self.platform,
                            ticker=self.ticker,
                            content=text[:2000],   # 截断过长内容
                            author_id=str(submission.author),
                            author_followers=submission.score,
                            likes=submission.ups,
                            published_at=published,
                            raw={"id": submission.id, "url": submission.url},
                        ))

                        # 采集高赞评论
                        submission.comments.replace_more(limit=0)
                        for comment in list(submission.comments)[:5]:
                            if comment.score < 3:
                                continue
                            comments.append(RawComment(
                                platform=self.platform,
                                ticker=self.ticker,
                                content=comment.body[:1000],
                                author_id=str(comment.author),
                                author_followers=0,
                                likes=comment.score,
                                published_at=datetime.fromtimestamp(comment.created_utc),
                                raw={"id": comment.id},
                            ))

                except Exception as e:
                    logger.warning("[Reddit] r/%s keyword=%s 失败: %s", subreddit_name, keyword, e)

        logger.info("Reddit 采集完成：共 %d 条", len(comments))
        return comments
