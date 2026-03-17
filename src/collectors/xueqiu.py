"""
src/collectors/xueqiu.py — 雪球数据采集器（基于 pysnowball）

使用 pysnowball 库通过 xq_a_token 认证访问雪球 API，
采集指定股票的社交帖子、实时行情及财务摘要。

配置：XUEQIU_COOKIES 环境变量，支持两种格式：
  1. 纯 token 字符串（仅 xq_a_token 的值）
  2. 完整 cookie 字符串：xq_a_token=xxx; xq_r_token=yyy; ...

雪球港股代码格式：HK + 五位代码（如 1860.HK → HK01860）
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pysnowball

from config.settings import settings
from src.collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)

# 雪球社交 timeline API
TIMELINE_URL = "https://xueqiu.com/v4/statuses/public_timeline_by_symbol.json"
XUEQIU_HOST = "xueqiu.com"


def _ticker_to_xueqiu_symbol(ticker: str) -> str:
    """
    将 Yahoo Finance 格式代码转为雪球格式。
    1860.HK → HK01860
    APP / U  → 直接大写（美股无需前缀）
    """
    if ticker.endswith(".HK"):
        code = ticker.replace(".HK", "").zfill(5)
        return f"HK{code}"
    return ticker.upper()


def _extract_token(raw: str) -> str:
    """
    从 cookie 字符串中提取 xq_a_token 的值。
    支持：
      - 纯 token 值（不含 =）
      - xq_a_token=xxx; ...
    """
    raw = raw.strip()
    if "=" not in raw:
        return raw  # 直接就是 token 值

    match = re.search(r"xq_a_token=([^;]+)", raw)
    if match:
        return match.group(1).strip()

    # 找不到 xq_a_token，取第一个 key=value 的 value
    first = raw.split(";")[0]
    return first.split("=", 1)[1].strip() if "=" in first else raw


class XueqiuCollector(BaseCollector):
    """
    雪球采集器：社交帖子 + 实时行情。

    认证方式：pysnowball.set_token(xq_a_token)
    社交帖子：通过 httpx 调用雪球 timeline API
    行情数据：通过 pysnowball.quote_detail / realtime
    """

    platform = "xueqiu"

    def __init__(self) -> None:
        super().__init__()
        self._token: str | None = None
        self._symbol = _ticker_to_xueqiu_symbol(settings.primary_ticker)

    def _setup_token(self) -> bool:
        """
        从 XUEQIU_COOKIES 环境变量读取 xq_a_token 并设置 pysnowball。
        变量值直接就是 xq_a_token 的值（repository variable 格式）。
        """
        import os
        # 优先读 pydantic settings，fallback 到直接读环境变量
        raw = settings.xueqiu_cookies.strip() or os.environ.get("XUEQIU_COOKIES", "").strip()
        if not raw:
            self.logger.warning("XUEQIU_COOKIES 未配置，雪球采集将跳过")
            return False

        # 支持两种格式：
        #   1. 纯 token 值（repository variable 推荐格式）
        #   2. 完整 cookie 字符串（含 xq_a_token=xxx）
        token = _extract_token(raw)
        self._token = token
        pysnowball.set_token(token)
        self.logger.info("雪球 xq_a_token 已配置（长度: %d）", len(token))
        return True

    def _fetch_timeline(self, count: int = 20) -> list[dict[str, Any]]:
        """同步获取股票 timeline 帖子（requests，与 pysnowball 保持一致）。"""
        import requests

        headers = {
            "Host": XUEQIU_HOST,
            "Cookie": f"xq_a_token={self._token}",
            "User-Agent": "Xueqiu iPhone 14.15.1",
            "Accept": "application/json",
            "Accept-Language": "zh-Hans-CN;q=1",
            "Accept-Encoding": "gzip, deflate",
            "Referer": f"https://xueqiu.com/S/{self._symbol}",
        }
        resp = requests.get(
            TIMELINE_URL,
            params={"count": count, "symbol": self._symbol},
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            raise CollectorError(f"雪球 timeline API 返回 {resp.status_code}")

        data = resp.json()
        return data.get("statuses", [])

    def _fetch_quote(self) -> dict[str, Any]:
        """同步获取实时行情（pysnowball）。"""
        try:
            result = pysnowball.quote_detail(self._symbol)
            quote = result.get("data", {}).get("quote", {})
            return quote
        except Exception as e:
            self.logger.warning("行情获取失败: %s", e)
            return {}

    def _parse_post(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """将雪球原始帖子转为统一格式。"""
        text = raw.get("text") or raw.get("description") or ""
        # 去除 HTML 标签
        text = re.sub(r"<[^>]+>", "", text).strip()
        if not text:
            return None

        user = raw.get("user") or {}
        created_ms = raw.get("created_at")
        captured_at = (
            datetime.fromtimestamp(created_ms / 1000, tz=UTC).isoformat()
            if created_ms
            else datetime.now(UTC).isoformat()
        )

        return {
            "platform": self.platform,
            "ticker": settings.primary_ticker,
            "external_id": str(raw.get("id", "")),
            "content": text[:1000],
            "author": user.get("screen_name") or user.get("id"),
            "captured_at": captured_at,
            "score": None,
            "sentiment": None,
            "topics": [],
            "confidence": None,
        }

    async def collect(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """采集雪球帖子 + 行情（通过 pysnowball 认证）。"""
        if not self._setup_token():
            return []

        loop = asyncio.get_event_loop()

        # 1. 采集社交帖子
        try:
            raw_posts = await loop.run_in_executor(None, self._fetch_timeline)
        except CollectorError as e:
            raise
        except Exception as e:
            raise CollectorError(f"雪球帖子采集失败: {e}") from e

        results: list[dict[str, Any]] = []
        for raw in raw_posts:
            parsed = self._parse_post(raw)
            if parsed is None:
                continue
            # 增量过滤
            if since:
                try:
                    post_time = datetime.fromisoformat(parsed["captured_at"])
                    if post_time < since:
                        continue
                except Exception:
                    pass
            results.append(parsed)

        self.logger.info(
            "雪球帖子采集完成：共 %d 条（symbol=%s，since=%s）",
            len(results),
            self._symbol,
            since.isoformat() if since else "全量",
        )

        # 2. 采集行情（附加到日志，不算入 sentiment records）
        quote = await loop.run_in_executor(None, self._fetch_quote)
        if quote:
            self.logger.info(
                "雪球行情 %s: 现价=%s 涨跌幅=%s%%",
                self._symbol,
                quote.get("current"),
                quote.get("percent"),
            )

        return results
