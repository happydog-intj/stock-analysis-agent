"""
scripts/backfill.py — 历史数据回填脚本

用于初始化历史行情数据，支持：
  - 回填指定标的的 N 天 OHLCV 历史数据
  - 批量写入 competitor_snapshots 表
  - 避免重复插入（upsert by ticker + trade_date）

使用方法：
    python scripts/backfill.py --ticker 1860.HK --days 30
    python scripts/backfill.py --all-tickers --days 90
    python scripts/backfill.py --ticker APP,U,APPS --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from src.db.database import close_db, get_session, init_db  # noqa: E402
from src.db.models import CompetitorSnapshot  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill")


async def backfill_ticker(ticker: str, days: int) -> int:
    """
    回填单个标的的历史 OHLCV 数据。

    Args:
        ticker: Yahoo Finance 标的代码
        days:   回填天数

    Returns:
        写入的记录数

    TODO: 实现 upsert（ON CONFLICT (ticker, trade_date) DO UPDATE）
    TODO: 支持调整历史数据（处理股息/拆股）
    """
    import yfinance as yf

    logger.info("开始回填 %s，历史 %d 天", ticker, days)

    try:
        ticker_obj = yf.Ticker(ticker)
        # 拉取历史数据
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)
        hist = ticker_obj.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )

        if hist.empty:
            logger.warning("%s 无历史数据", ticker)
            return 0

        # 获取基本面数据（所有历史日用同一份，因为 yfinance 无历史基本面）
        info = ticker_obj.info or {}
        market_cap = info.get("marketCap")
        revenue_ttm = info.get("totalRevenue")
        pe_ratio = info.get("trailingPE")
        ps_ratio = info.get("priceToSalesTrailing12Months")

        records: list[CompetitorSnapshot] = []
        prev_close = None

        for date, row in hist.iterrows():
            trade_date = str(date.date())
            curr_close = float(row["Close"])

            change_pct = None
            if prev_close and prev_close != 0:
                change_pct = round((curr_close - prev_close) / prev_close * 100, 2)
            prev_close = curr_close

            records.append(
                CompetitorSnapshot(
                    ticker=ticker,
                    trade_date=trade_date,
                    price=round(curr_close, 4),
                    open_price=round(float(row["Open"]), 4),
                    high_price=round(float(row["High"]), 4),
                    low_price=round(float(row["Low"]), 4),
                    volume=float(row["Volume"]),
                    change_pct=change_pct,
                    market_cap=market_cap,
                    revenue_ttm=revenue_ttm,
                    pe_ratio=pe_ratio,
                    ps_ratio=ps_ratio,
                    captured_at=datetime.now(UTC),
                )
            )

        # 批量写入 DB
        # TODO: 替换为 upsert（避免重复执行时报 unique constraint）
        async with get_session() as session:
            for record in records:
                session.add(record)

        logger.info("%s 回填完成，写入 %d 条记录", ticker, len(records))
        return len(records)

    except Exception as e:
        logger.exception("%s 回填失败: %s", ticker, e)
        return 0


async def main(args: argparse.Namespace) -> None:
    """回填主流程。"""
    # 初始化 DB（若表不存在则创建）
    await init_db()

    # 确定要回填的标的列表
    if args.all_tickers:
        tickers = settings.all_tickers
    elif args.ticker:
        tickers = [t.strip() for t in args.ticker.split(",")]
    else:
        logger.error("请指定 --ticker 或 --all-tickers")
        return

    logger.info("回填标的: %s，历史天数: %d", tickers, args.days)

    total = 0
    for ticker in tickers:
        count = await backfill_ticker(ticker, args.days)
        total += count

    await close_db()
    logger.info("✅ 回填完成，共写入 %d 条记录", total)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="历史数据回填工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--ticker",
        type=str,
        help="指定标的（逗号分隔，如 '1860.HK,APP,U'）",
    )
    group.add_argument(
        "--all-tickers",
        action="store_true",
        help="回填所有配置标的（primary + competitors）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="回填天数（默认 30）",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
