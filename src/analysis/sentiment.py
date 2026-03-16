"""
src/analysis/sentiment.py — Claude API 情绪分析引擎

批量分析评论/帖子文本，输出：
  - score:      情绪分 -100（极度悲观） ~ +100（极度乐观）
  - sentiment:  情绪标签（very_bullish / bullish / neutral / bearish / very_bearish）
  - topics:     提炼的主题列表（如 ["广告收入", "回购", "Mintegral增速"]）
  - confidence: 分析置信度 0 ~ 1.0

缓存策略：
  - 使用 Redis 对相同内容的分析结果缓存 1 小时（避免重复调用 API）
  - 缓存键：sha256(content)[:16]
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timezone
from typing import Any

import anthropic
import redis.asyncio as aioredis

from config.settings import settings

logger = logging.getLogger(__name__)

# Claude 系统 Prompt：角色定义与输出格式约束
SYSTEM_PROMPT = """你是一位专业的港股市场情绪分析师，专注于汇量科技（汇量科技集团，股票代码 1860.HK，品牌 Mobvista/Mintegral）。

你的任务是分析给定的中英文评论文本，判断其对汇量科技股价的情绪倾向。

## 输出格式（严格 JSON，不要有任何 markdown 包裹）

{
  "results": [
    {
      "index": 0,
      "score": 65,
      "sentiment": "bullish",
      "topics": ["广告收入增长", "Mintegral市占率"],
      "confidence": 0.85,
      "reasoning": "简短说明判断依据（中文，50字内）"
    }
  ]
}

## 评分规则

| 分值范围    | sentiment 标签  | 含义           |
|------------|-----------------|----------------|
| 70 ~ 100   | very_bullish    | 强烈看多       |
| 30 ~ 69    | bullish         | 看多           |
| -29 ~ 29   | neutral         | 中性           |
| -69 ~ -30  | bearish         | 看空           |
| -100 ~ -70 | very_bearish    | 强烈看空       |

## 注意事项
- 只分析与汇量科技/程序化广告行业相关的内容
- 无关内容输出 score=0, sentiment=neutral, confidence=0.1
- topics 最多 3 个，每个不超过 10 字
"""


class SentimentAnalyzer:
    """
    基于 Claude API 的情绪分析器，带 Redis 缓存。

    用法::
        analyzer = SentimentAnalyzer()
        results = await analyzer.analyze_batch(comments)
    """

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None
        self._redis: aioredis.Redis | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        """懒初始化 Anthropic 客户端。"""
        if self._client is None:
            if not settings.claude_api_key:
                raise RuntimeError("CLAUDE_API_KEY 未配置")
            self._client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
        return self._client

    async def _get_redis(self) -> aioredis.Redis:
        """懒初始化 Redis 连接。"""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    @staticmethod
    def _cache_key(content: str) -> str:
        """生成内容的缓存键（SHA256 前 16 位）。"""
        return "sentiment:" + hashlib.sha256(content.encode()).hexdigest()[:16]

    async def _get_cached(self, content: str) -> dict[str, Any] | None:
        """
        从 Redis 缓存读取已分析结果。

        Returns:
            缓存命中返回结果字典，否则返回 None
        """
        try:
            redis = await self._get_redis()
            cached = await redis.get(self._cache_key(content))
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning("读取缓存失败: %s", e)
        return None

    async def _set_cached(self, content: str, result: dict[str, Any]) -> None:
        """将分析结果写入 Redis 缓存。"""
        try:
            redis = await self._get_redis()
            await redis.setex(
                self._cache_key(content),
                settings.redis_cache_ttl,
                json.dumps(result, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning("写入缓存失败: %s", e)

    async def _call_claude(self, texts: list[str]) -> list[dict[str, Any]]:
        """
        批量调用 Claude API 分析情绪。

        Args:
            texts: 待分析文本列表（最多 batch_size 条）

        Returns:
            与 texts 等长的分析结果列表

        TODO: 实现 token 计数，防止超过上下文窗口限制
        TODO: 添加指数退避重试（anthropic.RateLimitError）
        TODO: 支持 streaming 模式以减少首字节延迟
        """
        client = self._get_client()

        # 构造批量分析的用户消息
        user_content = "请分析以下评论，按 JSON 格式输出：\n\n"
        for i, text in enumerate(texts):
            user_content += f"[{i}] {text[:500]}\n\n"  # 截断超长文本

        try:
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=settings.claude_max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )

            # 解析 Claude 返回的 JSON
            raw_text = response.content[0].text.strip()
            # TODO: 更健壮的 JSON 提取（处理 Claude 偶发的 markdown 包裹）
            data = json.loads(raw_text)
            return data.get("results", [])

        except json.JSONDecodeError as e:
            logger.error("Claude 响应 JSON 解析失败: %s", e)
            # 降级：为所有输入返回中性结果
            return [
                {
                    "index": i,
                    "score": 0,
                    "sentiment": "neutral",
                    "topics": [],
                    "confidence": 0.0,
                    "reasoning": "解析失败",
                }
                for i in range(len(texts))
            ]

    async def analyze_batch(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        批量分析评论情绪，自动分批（每批 batch_size 条）并利用缓存。

        Args:
            records: 含 content 字段的评论字典列表

        Returns:
            为每条记录添加了情绪分析字段的新列表：
              score, sentiment, topics, confidence, analyzed_at

        Example::
            results = await analyzer.analyze_batch([
                {"content": "Mintegral 增速超预期，看好明年业绩", ...},
                {"content": "广告行业整体低迷，1860 压力大", ...},
            ])
        """
        if not records:
            return []

        batch_size = settings.claude_batch_size
        enriched: list[dict[str, Any]] = []

        for batch_start in range(0, len(records), batch_size):
            batch = records[batch_start : batch_start + batch_size]
            texts = [r.get("content", "") for r in batch]

            # 检查缓存
            cached_results: dict[int, dict[str, Any]] = {}
            uncached_indices: list[int] = []

            for i, text in enumerate(texts):
                cached = await self._get_cached(text)
                if cached:
                    cached_results[i] = cached
                else:
                    uncached_indices.append(i)

            # 仅对未缓存的内容调用 Claude
            api_results: dict[int, dict[str, Any]] = {}
            if uncached_indices:
                uncached_texts = [texts[i] for i in uncached_indices]
                logger.info(
                    "调用 Claude 分析 %d 条（共 %d 条，%d 条命中缓存）",
                    len(uncached_texts),
                    len(texts),
                    len(cached_results),
                )
                raw_results = await self._call_claude(uncached_texts)
                for j, result in enumerate(raw_results):
                    orig_idx = uncached_indices[j]
                    api_results[orig_idx] = result
                    # 写入缓存
                    await self._set_cached(texts[orig_idx], result)

            # 合并结果并回填到原始记录
            for i, record in enumerate(batch):
                analysis = cached_results.get(i) or api_results.get(i, {})
                enriched_record = {
                    **record,
                    "score": analysis.get("score"),
                    "sentiment": analysis.get("sentiment"),
                    "topics": analysis.get("topics", []),
                    "confidence": analysis.get("confidence"),
                    "analyzed_at": datetime.now(UTC).isoformat(),
                }
                enriched.append(enriched_record)

        logger.info("情绪分析完成，共 %d 条记录", len(enriched))
        return enriched

    async def analyze_single(self, content: str) -> dict[str, Any]:
        """
        分析单条文本。

        Returns:
            单条分析结果字典。
        """
        results = await self.analyze_batch([{"content": content}])
        return results[0] if results else {}

    async def close(self) -> None:
        """释放资源。"""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
