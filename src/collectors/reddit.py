"""
src/collectors/reddit.py — Reddit 帖子采集器

使用 PRAW（Python Reddit API Wrapper）监控以下 Subreddit：
  - r/HKStocks
  - r/stocks
  - r/investing

关键词过滤：Mobvista / 1860.HK / Mintegral / 汇量

依赖：
    pip install praw
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any

import praw
import praw.models

from config.settings import settings
from src.collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    """
    Reddit 帖子与评论采集器（PRAW + asyncio run_in_executor）。

    PRAW 是同步库，通过 run_in_executor 在线程池中运行，避免阻塞事件循环。
    增量策略：使用帖子的 UTC 时间戳作为游标。
    """

    platform = "reddit"

    def __init__(self) -> None:
        super().__init__()
        self._reddit: praw.Reddit | None = None

    def _get_reddit(self) -> praw.Reddit:
        """懒初始化 PRAW Reddit 实例。"""
        if self._reddit is None:
            if not settings.reddit_client_id:
                raise CollectorError("REDDIT_CLIENT_ID 未配置")
            self._reddit = praw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent,
                # 只读模式，不需要 username/password
                # TODO: 如需访问私密 subreddit，则需要提供账号
            )
            self._reddit.read_only = True
            self.logger.info("Reddit 客户端初始化成功")
        return self._reddit

    def _is_relevant(self, text: str) -> bool:
        """
        检查文本是否包含目标关键词（大小写不敏感）。

        TODO: 支持正则/模糊匹配，提高召回率
        """
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in settings.reddit_keywords)

    def _parse_submission(self, submission: praw.models.Submission) -> dict[str, Any]:
        """
        解析 Reddit 帖子为统一格式。

        TODO: 同步采集帖子下的顶层评论
        """
        created_at = datetime.fromtimestamp(
            submission.created_utc, tz=timezone.utc
        ).isoformat()
        return {
            "platform": self.platform,
            "ticker": settings.primary_ticker,
            "external_id": submission.id,
            "content": f"{submission.title}\n\n{submission.selftext or ''}".strip()[:3000],
            "author": str(submission.author) if submission.author else "[deleted]",
            "captured_at": created_at,
            "url": f"https://reddit.com{submission.permalink}",
            "subreddit": submission.subreddit.display_name,
            "score": submission.score,
            "num_comments": submission.num_comments,
        }

    def _sync_collect(self, since_ts: float | None = None) -> list[dict[str, Any]]:
        """
        同步采集逻辑（在线程池中执行）。

        Args:
            since_ts: Unix 时间戳（秒），只返回 created_utc >= since_ts 的帖子。
                      为 None 时不做时间过滤。

        策略：
          - 对每个目标 Subreddit 搜索关键词
          - time_filter 根据 since 自动选择（今日→day，否则→week）
          - 合并结果并去重

        TODO: 支持搜索帖子内的评论文本
        TODO: 实现 stream 模式，实时监控新帖子
        """
        reddit = self._get_reddit()
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        query       = " OR ".join(settings.reddit_keywords)
        time_filter = "day" if since_ts else "week"   # 今日任务用 day，减少 API 用量

        for sub_name in settings.reddit_subreddits:
            try:
                subreddit = reddit.subreddit(sub_name)
                for submission in subreddit.search(
                    query,
                    sort="new",
                    time_filter=time_filter,
                    limit=50,
                ):
                    if submission.id in seen_ids:
                        continue
                    seen_ids.add(submission.id)

                    # ① 时间窗口过滤
                    if since_ts and submission.created_utc < since_ts:
                        continue

                    # ② 关键词二次过滤
                    full_text = f"{submission.title} {submission.selftext or ''}"
                    if not self._is_relevant(full_text):
                        continue

                    results.append(self._parse_submission(submission))

            except Exception as e:
                self.logger.warning("搜索 r/%s 失败: %s", sub_name, e)

        return results

    async def collect(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """
        执行一次 Reddit 采集（异步包装同步逻辑）。

        Args:
            since: 只返回该时间点之后发布的帖子。
                   定时任务传入当天 00:00 HKT，仅采集今日评论。
        """
        self.logger.info("Reddit 采集开始，since=%s", since.isoformat() if since else "全量")

        since_ts: float | None = since.timestamp() if since else None

        loop = asyncio.get_event_loop()
        try:
            posts = await loop.run_in_executor(
                None, partial(self._sync_collect, since_ts)
            )
        except CollectorError:
            raise
        except Exception as e:
            raise CollectorError(f"Reddit 采集失败: {e}") from e

        self.logger.info("Reddit 采集完成，%d 条", len(posts))
        return posts
