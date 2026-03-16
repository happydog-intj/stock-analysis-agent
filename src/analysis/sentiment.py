"""
情绪分析模块：使用 LLM 对评论进行批量情绪评分。

无状态设计：不依赖 Redis/数据库，直接调用 LLM。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from src.analysis.llm_client import BaseLLMClient, create_llm_client

logger = logging.getLogger(__name__)

SENTIMENT_PROMPT = """你是一位专业的港股投资情绪分析师。请分析以下股票评论的情绪倾向。

股票代码：{ticker}
平台：{platform}

评论列表（JSON 数组）：
{comments}

请对每条评论输出以下 JSON 结构（数组，顺序与输入对应）：
[
  {{
    "score": <整数，-100（极度悲观）到 100（极度乐观）>,
    "sentiment": "<bullish | bearish | neutral>",
    "topics": ["<话题1>", "<话题2>"],
    "confidence": <0.0 到 1.0 的浮点数>
  }}
]

评分参考：
- 80~100：强烈看多，充满信心
- 40~79 ：偏多，有一定正面预期
- -39~39：中性，观望或信息不足
- -79~-40：偏空，有担忧
- -100~-80：强烈看空，非常悲观

话题分类参考（选最相关的 1-3 个）：
revenue（营收）/ competition（竞争）/ valuation（估值）/ guidance（展望）/
management（管理层）/ dividend（分红）/ product（产品）/ macro（宏观）

只输出 JSON 数组，不要任何额外说明。"""


@dataclass
class SentimentResult:
    score:       float            # -100 ~ 100
    sentiment:   str              # bullish / bearish / neutral
    topics:      list[str]
    confidence:  float            # 0.0 ~ 1.0
    raw_comment: str = field(default="", repr=False)


class SentimentAnalyzer:
    """批量情绪分析器（无状态，直接调用 LLM）。"""

    BATCH_SIZE = 20

    def __init__(self, llm_client: BaseLLMClient | None = None) -> None:
        self._llm = llm_client or create_llm_client()
        logger.info("SentimentAnalyzer 使用 [%s/%s]", self._llm.provider, self._llm.model)

    async def _call_llm(
        self,
        comments: list[str],
        ticker: str,
        platform: str,
    ) -> list[SentimentResult]:
        prompt = SENTIMENT_PROMPT.format(
            ticker=ticker,
            platform=platform,
            comments=json.dumps(comments, ensure_ascii=False, indent=2),
        )
        try:
            text = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.2,
            )
            parsed: list[dict] = json.loads(text)
            return [
                SentimentResult(
                    score=float(item.get("score", 0)),
                    sentiment=item.get("sentiment", "neutral"),
                    topics=item.get("topics", []),
                    confidence=float(item.get("confidence", 0.5)),
                    raw_comment=comments[i],
                )
                for i, item in enumerate(parsed)
            ]
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            # 失败时返回中性结果，不阻断流程
            return [
                SentimentResult(score=0, sentiment="neutral", topics=[], confidence=0.0, raw_comment=c)
                for c in comments
            ]

    async def analyze_batch(
        self,
        comments: list[str],
        ticker: str = "1860.HK",
        platform: str = "unknown",
    ) -> list[SentimentResult]:
        """批量分析评论情绪，按 BATCH_SIZE 分批调用 LLM。"""
        if not comments:
            return []

        logger.info("情绪分析 | [%s] %d 条评论，分 %d 批",
                    platform, len(comments), -(-len(comments) // self.BATCH_SIZE))

        results: list[SentimentResult] = []
        for batch_start in range(0, len(comments), self.BATCH_SIZE):
            batch = comments[batch_start : batch_start + self.BATCH_SIZE]
            batch_results = await self._call_llm(batch, ticker, platform)
            results.extend(batch_results)

        return results

    @staticmethod
    def aggregate(
        results: list[SentimentResult],
        platform_weight: float = 1.0,
    ) -> dict:
        """聚合多条评论的情绪分数。"""
        if not results:
            return {"avg_score": 0.0, "distribution": {}, "top_topics": []}

        weighted_scores = [r.score * r.confidence * platform_weight for r in results]
        avg = sum(weighted_scores) / len(weighted_scores)

        dist: dict[str, int] = {"bullish": 0, "neutral": 0, "bearish": 0}
        topic_counts: dict[str, int] = {}
        for r in results:
            dist[r.sentiment] = dist.get(r.sentiment, 0) + 1
            for t in r.topics:
                topic_counts[t] = topic_counts.get(t, 0) + 1

        top_topics = sorted(topic_counts.items(), key=lambda x: -x[1])[:5]
        return {
            "avg_score": round(avg, 2),
            "distribution": dist,
            "top_topics": [{"topic": t, "count": c} for t, c in top_topics],
        }
