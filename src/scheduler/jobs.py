"""
定时任务：每日 09:00 晨报 / 12:00 午报 / 15:00 收盘报。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.analysis.sentiment import SentimentAnalyzer
from src.collectors.hkex import HKEXCollector
from src.collectors.reddit import RedditCollector
from src.collectors.xueqiu import XueqiuCollector
from src.collectors.yahoo_finance import YahooFinanceCollector
from src.reporters.feishu import FeishuReporter
from src.reporters.templates import ReportContext

logger = logging.getLogger(__name__)

# 平台权重
PLATFORM_WEIGHTS = {
    "xueqiu": 0.35,
    "futu":   0.25,
    "tiger":  0.20,
    "reddit": 0.15,
}

TICKER = "1860.HK"


def _today_start() -> datetime:
    """返回今天 00:00:00 HKT（带时区）。定时任务用此作为评论采集窗口起点。"""
    HKT = ZoneInfo("Asia/Hong_Kong")
    return datetime.combine(date.today(), time.min, tzinfo=HKT)


async def _build_report_context(period: str) -> ReportContext:
    """采集当日数据，构建报告上下文。

    评论采集只取今天 00:00 HKT 之后发布的内容，避免重复分析历史数据。
    行情数据（Yahoo Finance）和公告（HKEX）不受此限制，仍采集最新状态。
    """
    analyzer     = SentimentAnalyzer()
    yf_collector = YahooFinanceCollector()
    hkex         = HKEXCollector()

    # 今日 00:00 HKT — 所有评论采集的时间窗口起点
    today_start = _today_start()
    logger.info("报告周期=%s，评论时间窗口 since=%s", period, today_start.isoformat())

    # 并发采集（评论类传入 since=today_start，行情/公告不需要）
    xueqiu_task  = XueqiuCollector().run_once(since=today_start)
    reddit_task  = RedditCollector().run_once(since=today_start)
    yf_task      = yf_collector.get_daily_snapshots()
    hkex_task    = hkex.poll()

    xueqiu_comments, reddit_comments, stock_snaps, announcements = await asyncio.gather(
        xueqiu_task, reddit_task, yf_task, hkex_task,
        return_exceptions=True,
    )

    # 安全取值（gather 可能返回异常）
    xueqiu_comments = xueqiu_comments if isinstance(xueqiu_comments, list) else []
    reddit_comments = reddit_comments if isinstance(reddit_comments, list) else []
    stock_snaps     = stock_snaps if isinstance(stock_snaps, list) else []
    announcements   = announcements if isinstance(announcements, list) else []

    # 情绪分析
    platform_scores: dict[str, float] = {}
    all_weighted_scores: list[float]  = []

    for platform, comments in [("xueqiu", xueqiu_comments), ("reddit", reddit_comments)]:
        if not comments:
            logger.info("[%s] 今日无新评论，跳过情绪分析", platform)
            continue
        # comments 是 list[dict]，取 "content" 字段
        texts   = [c["content"] for c in comments if c.get("content")]
        if not texts:
            continue
        results = await analyzer.analyze_batch(texts, ticker=TICKER, platform=platform)
        agg     = analyzer.aggregate(results, PLATFORM_WEIGHTS.get(platform, 0.1))
        score   = agg["avg_score"]
        platform_scores[platform] = score
        all_weighted_scores.extend(
            [r.score * r.confidence * PLATFORM_WEIGHTS.get(platform, 0.1) for r in results]
        )

    sentiment_score = (
        sum(all_weighted_scores) / len(all_weighted_scores)
        if all_weighted_scores else 0.0
    )

    # 取汇量科技的股价数据
    mobvista_snap = next((s for s in stock_snaps if "1860" in s.ticker), None)
    price      = mobvista_snap.close     if mobvista_snap else 0.0
    prev_close = mobvista_snap.prev_close if mobvista_snap else 0.0
    change_pct = mobvista_snap.change_pct if mobvista_snap else 0.0
    volume     = mobvista_snap.volume    if mobvista_snap else 0

    competitor_table = await yf_collector.get_competitor_table()

    # 风险信号检测
    risk_signals: list[str] = []
    if xueqiu_comments and platform_scores.get("xueqiu", 0) < -30:
        risk_signals.append("雪球负面情绪显著上升，请关注")
    if change_pct < -3:
        risk_signals.append(f"今日股价下跌 {change_pct:.1f}%，跌幅较大")
    for ann in announcements:
        from src.collectors.hkex import AnnouncementPriority
        if ann.priority == AnnouncementPriority.HIGH:
            risk_signals.append(f"高优先级公告：{ann.title}")

    # 热点话题：复用上方已分析过的 results，无需重复调用 LLM
    # 合并所有平台当日评论文本再做一次聚合分析
    from src.analysis.sentiment import SentimentResult
    all_today_texts: list[str] = []
    for comments in [xueqiu_comments, reddit_comments]:
        all_today_texts.extend(c["content"] for c in comments if c.get("content"))

    if all_today_texts:
        all_results: list[SentimentResult] = await analyzer.analyze_batch(
            all_today_texts, ticker=TICKER, platform="all"
        )
        agg_all    = analyzer.aggregate(all_results)
        top_topics = agg_all.get("top_topics", [])
    else:
        top_topics = []

    return ReportContext(
        ticker=TICKER,
        price=price,
        prev_close=prev_close,
        change_pct=change_pct,
        volume=volume,
        sentiment_score=round(sentiment_score, 1),
        platform_scores=platform_scores,
        top_topics=top_topics,
        risk_signals=risk_signals,
        competitor_table=competitor_table,
        announcements=[ann.title for ann in announcements],
        period=period,
        timestamp=datetime.now(),
    )


async def morning_report() -> None:
    """09:00 盘前晨报。"""
    logger.info("开始生成晨报...")
    try:
        ctx = await _build_report_context("morning")
        reporter = FeishuReporter()
        await reporter.send_morning_report(ctx)
        logger.info("晨报推送完成")
    except Exception as e:
        logger.error("晨报生成失败: %s", e, exc_info=True)


async def noon_report() -> None:
    """12:00 盘中午报。"""
    logger.info("开始生成午报...")
    try:
        ctx = await _build_report_context("noon")
        reporter = FeishuReporter()
        await reporter.send_noon_report(ctx)
        logger.info("午报推送完成")
    except Exception as e:
        logger.error("午报生成失败: %s", e, exc_info=True)


async def close_report() -> None:
    """15:00 收盘报。"""
    logger.info("开始生成收盘报...")
    try:
        ctx = await _build_report_context("close")
        reporter = FeishuReporter()
        await reporter.send_close_report(ctx)
        logger.info("收盘报推送完成")
    except Exception as e:
        logger.error("收盘报生成失败: %s", e, exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """创建并配置 APScheduler。"""
    scheduler = AsyncIOScheduler(timezone="Asia/Hong_Kong")

    scheduler.add_job(
        morning_report,
        CronTrigger(hour=9, minute=0),
        id="morning_report",
        name="晨报（盘前）",
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        noon_report,
        CronTrigger(hour=12, minute=0),
        id="noon_report",
        name="午报（盘中）",
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        close_report,
        CronTrigger(hour=15, minute=0),
        id="close_report",
        name="收盘报（盘后）",
        max_instances=1,
        misfire_grace_time=300,
    )

    return scheduler
