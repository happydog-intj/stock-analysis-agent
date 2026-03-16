"""
src/collectors/yahoo_finance.py — Yahoo Finance 行情采集器

使用 yfinance 库同步拉取以下标的的 OHLCV 日线数据：
  - 1860.HK  汇量科技（主标的）
  - APP       AppLovin
  - U         Unity Technologies
  - APPS      Digital Turbine

同时获取基本面指标（市值、PE、PS、TTM 营收）用于竞对对比。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timezone
from typing import Any

import yfinance as yf

from config.settings import settings
from src.collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)


class YahooFinanceCollector(BaseCollector):
    """
    Yahoo Finance 行情数据采集器。

    数据来源：yfinance（非官方 Yahoo Finance Python 封装）
    采集频率：每日收盘后一次（由调度器触发）
    增量策略：记录最后同步的交易日期（YYYY-MM-DD）
    """

    platform = "yahoo_finance"

    @property
    def tickers(self) -> list[str]:
        """所有需要采集的标的列表（主标的 + 竞对）。"""
        return settings.all_tickers

    def _fetch_daily_ohlcv(self, ticker: str) -> dict[str, Any] | None:
        """
        同步获取单个标的的最新交易日 OHLCV 数据。

        Args:
            ticker: Yahoo Finance 标的代码（如 "1860.HK"）

        Returns:
            行情字典，若无数据则返回 None

        TODO: 支持批量下载（yf.download 批量更高效）
        TODO: 处理港股 .HK 后缀的特殊逻辑（交易日历）
        """
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="2d")  # 取最近 2 天以防节假日

            if hist.empty:
                logger.warning("[%s] 无历史数据", ticker)
                return None

            latest = hist.iloc[-1]
            trade_date = str(hist.index[-1].date())

            # 基本面数据（可能为 None）
            info = ticker_obj.info or {}
            market_cap = info.get("marketCap")
            revenue_ttm = info.get("totalRevenue")
            pe_ratio = info.get("trailingPE")
            ps_ratio = info.get("priceToSalesTrailing12Months")

            # 计算涨跌幅（与前一交易日对比）
            change_pct: float | None = None
            if len(hist) >= 2:
                prev_close = hist.iloc[-2]["Close"]
                curr_close = latest["Close"]
                if prev_close and prev_close != 0:
                    change_pct = round((curr_close - prev_close) / prev_close * 100, 2)

            return {
                "platform": self.platform,
                "ticker": ticker,
                "trade_date": trade_date,
                "price": round(float(latest["Close"]), 4),
                "open_price": round(float(latest["Open"]), 4),
                "high_price": round(float(latest["High"]), 4),
                "low_price": round(float(latest["Low"]), 4),
                "volume": float(latest["Volume"]),
                "change_pct": change_pct,
                "market_cap": market_cap,
                "revenue_ttm": revenue_ttm,
                "pe_ratio": pe_ratio,
                "ps_ratio": ps_ratio,
                "captured_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("[%s] 获取行情失败: %s", ticker, e)
            return None

    def _sync_collect_all(self) -> list[dict[str, Any]]:
        """
        同步采集所有标的的行情数据。

        TODO: 改用 yf.download(tickers, period='1d', group_by='ticker') 批量拉取
        """
        results: list[dict[str, Any]] = []
        for ticker in self.tickers:
            data = self._fetch_daily_ohlcv(ticker)
            if data:
                results.append(data)
        return results

    async def collect(self) -> list[dict[str, Any]]:
        """
        执行一次行情数据采集（异步包装同步 yfinance）。

        Returns:
            所有标的的最新行情快照列表。
        """
        last_trade_date = await self.get_last_id()
        self.logger.info("YahooFinance 采集开始，last_trade_date=%s", last_trade_date)

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, self._sync_collect_all)
        except Exception as e:
            raise CollectorError(f"Yahoo Finance 采集失败: {e}") from e

        if not results:
            return []

        # 增量过滤：跳过已采集的交易日
        new_results = [
            r
            for r in results
            if last_trade_date is None or r.get("trade_date", "") > last_trade_date
        ]

        if new_results:
            latest_date = max(r.get("trade_date", "") for r in new_results)
            await self.save_last_id(latest_date)

        self.logger.info(
            "YahooFinance 采集完成，%d 个标的，最新交易日: %s",
            len(new_results),
            max((r.get("trade_date", "") for r in new_results), default="N/A"),
        )
        return new_results
