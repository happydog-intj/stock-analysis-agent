"""
竞对股价数据采集：使用 yfinance 同步汇量科技及竞对的每日行情。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime

import yfinance as yf

logger = logging.getLogger(__name__)

# 关注的股票列表
WATCHLIST: dict[str, str] = {
    "1860.HK": "汇量科技",
    "APP":     "AppLovin",
    "U":       "Unity",
    "APPS":    "Digital Turbine",
    "DV":      "DoubleVerify",
}


@dataclass
class StockSnapshot:
    ticker:       str
    name:         str
    date:         date
    open:         float
    high:         float
    low:          float
    close:        float
    volume:       int
    prev_close:   float
    change_pct:   float        # 涨跌幅 %
    market_cap:   float | None = None
    pe_ratio:     float | None = None
    revenue_ttm:  float | None = None


class YahooFinanceCollector:
    """Yahoo Finance 行情采集器。"""

    async def get_daily_snapshots(self) -> list[StockSnapshot]:
        """异步获取所有关注股票的当日快照。"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_fetch)

    def _sync_fetch(self) -> list[StockSnapshot]:
        snapshots: list[StockSnapshot] = []
        for ticker, name in WATCHLIST.items():
            try:
                snap = self._fetch_one(ticker, name)
                if snap:
                    snapshots.append(snap)
            except Exception as e:
                logger.warning("[YFinance] %s 获取失败: %s", ticker, e)
        return snapshots

    def _fetch_one(self, ticker: str, name: str) -> StockSnapshot | None:
        yf_ticker = yf.Ticker(ticker)
        hist = yf_ticker.history(period="2d")
        if hist.empty or len(hist) < 1:
            return None

        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else last
        prev_close = float(prev["Close"])
        close      = float(last["Close"])
        change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0

        info = yf_ticker.info
        return StockSnapshot(
            ticker=ticker,
            name=name,
            date=last.name.date(),
            open=float(last["Open"]),
            high=float(last["High"]),
            low=float(last["Low"]),
            close=close,
            volume=int(last["Volume"]),
            prev_close=prev_close,
            change_pct=round(change_pct, 2),
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            revenue_ttm=info.get("totalRevenue"),
        )

    async def get_competitor_table(self) -> str:
        """生成竞对对比文本（用于报告）。"""
        snaps = await self.get_daily_snapshots()
        if not snaps:
            return "（数据获取失败）"

        lines = []
        for s in snaps:
            sign = "+" if s.change_pct >= 0 else ""
            bar = "▲" if s.change_pct >= 0 else "▼"
            lines.append(
                f"  {s.ticker:<10} {s.name:<12} "
                f"${s.close:.2f}  {bar} {sign}{s.change_pct:.1f}%"
            )
        return "\n".join(lines)
