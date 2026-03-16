"""
src/scheduler/jobs.py — APScheduler 定时任务定义

定义三个定时报告任务：
  - morning_report   每日 09:00 HKT
  - noon_report      每日 12:00 HKT
  - close_report     每日 15:00 HKT

以及两个持续采集任务：
  - collect_sentiment  每 5 分钟采集雪球/Reddit 评论
  - collect_market     每小时同步行情数据

使用 APScheduler AsyncIOScheduler，与 asyncio 事件循环集成。
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings

logger = logging.getLogger(__name__)


def _parse_time(time_str: str) -> tuple[int, int]:
    """解析 'HH:MM' 格式的时间字符串，返回 (hour, minute)。"""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def create_scheduler() -> AsyncIOScheduler:
    """
    创建并配置 APScheduler 实例。

    所有任务均以港股时区（Asia/Hong_Kong）为基准。
    """
    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

    # ── 延迟导入避免循环依赖 ────────────────────────────────────────────────
    from src.agents.orchestrator import Orchestrator

    orchestrator = Orchestrator()

    # ── 晨报：09:00 ─────────────────────────────────────────────────────────
    m_hour, m_min = _parse_time(settings.morning_report_time)
    scheduler.add_job(
        _run_report,
        trigger=CronTrigger(
            hour=m_hour,
            minute=m_min,
            timezone=settings.scheduler_timezone,
        ),
        id="morning_report",
        name="每日晨报（09:00 HKT）",
        kwargs={"orchestrator": orchestrator, "period": "morning"},
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,  # 延迟 5 分钟内仍执行
    )

    # ── 午报：12:00 ─────────────────────────────────────────────────────────
    n_hour, n_min = _parse_time(settings.noon_report_time)
    scheduler.add_job(
        _run_report,
        trigger=CronTrigger(
            hour=n_hour,
            minute=n_min,
            timezone=settings.scheduler_timezone,
        ),
        id="noon_report",
        name="每日午报（12:00 HKT）",
        kwargs={"orchestrator": orchestrator, "period": "noon"},
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # ── 收盘报：15:00 ────────────────────────────────────────────────────────
    c_hour, c_min = _parse_time(settings.close_report_time)
    scheduler.add_job(
        _run_report,
        trigger=CronTrigger(
            hour=c_hour,
            minute=c_min,
            timezone=settings.scheduler_timezone,
        ),
        id="close_report",
        name="每日收盘报（15:00 HKT）",
        kwargs={"orchestrator": orchestrator, "period": "close"},
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # ── 持续舆情采集：每 5 分钟 ──────────────────────────────────────────────
    scheduler.add_job(
        _collect_sentiment,
        trigger="interval",
        seconds=settings.collect_interval_xueqiu,
        id="collect_sentiment",
        name="持续舆情采集",
        kwargs={"orchestrator": orchestrator},
        max_instances=1,
        coalesce=True,
    )

    # ── 持续行情采集：每 10 分钟 ─────────────────────────────────────────────
    scheduler.add_job(
        _collect_market,
        trigger="interval",
        seconds=600,
        id="collect_market",
        name="持续行情采集",
        kwargs={"orchestrator": orchestrator},
        max_instances=1,
        coalesce=True,
    )

    # ── 港交所公告轮询：每 10 分钟 ──────────────────────────────────────────
    scheduler.add_job(
        _collect_hkex,
        trigger="interval",
        seconds=settings.collect_interval_hkex,
        id="collect_hkex",
        name="港交所公告轮询",
        kwargs={"orchestrator": orchestrator},
        max_instances=1,
        coalesce=True,
    )

    logger.info(
        "调度器配置完成：晨报 %s / 午报 %s / 收盘报 %s（%s）",
        settings.morning_report_time,
        settings.noon_report_time,
        settings.close_report_time,
        settings.scheduler_timezone,
    )
    return scheduler


# ── 任务函数 ──────────────────────────────────────────────────────────────────

async def _run_report(orchestrator: "Orchestrator", period: str) -> None:  # type: ignore[name-defined]
    """执行完整报告流程。"""
    try:
        await orchestrator.run_report(period=period)
    except Exception as e:
        logger.exception("报告任务 [%s] 执行失败: %s", period, e)


async def _collect_sentiment(orchestrator: "Orchestrator") -> None:  # type: ignore[name-defined]
    """执行一次舆情采集（雪球 + Reddit）。"""
    try:
        from src.agents.sentiment_agent import SentimentAgent
        # TODO: 先采集原始评论，再触发情绪分析
        await orchestrator.xueqiu.run_once()
        await orchestrator.reddit.run_once()
        # 分析未处理记录
        agent = SentimentAgent()
        await agent.run()
        await agent.close()
    except Exception as e:
        logger.exception("舆情采集失败: %s", e)


async def _collect_market(orchestrator: "Orchestrator") -> None:  # type: ignore[name-defined]
    """执行一次行情采集。"""
    try:
        await orchestrator.yahoo.run_once()
    except Exception as e:
        logger.exception("行情采集失败: %s", e)


async def _collect_hkex(orchestrator: "Orchestrator") -> None:  # type: ignore[name-defined]
    """执行一次港交所公告采集并触发告警检测。"""
    try:
        announcements = await orchestrator.hkex.run_once()
        if announcements:
            from src.agents.alert_agent import AlertAgent
            alert = AlertAgent()
            await alert.check_and_alert([], announcements)
    except Exception as e:
        logger.exception("HKEX 采集失败: %s", e)


# ── GitHub Actions 入口函数 ───────────────────────────────────────────────────
# run_job.py 通过 getattr(module, func_name) 动态调用这三个函数。

async def morning_report() -> None:
    """晨报入口（供 GitHub Actions / run_job.py 调用）。"""
    from src.agents.orchestrator import Orchestrator
    orchestrator = Orchestrator()
    await orchestrator.run_report(period="morning")


async def noon_report() -> None:
    """午报入口（供 GitHub Actions / run_job.py 调用）。"""
    from src.agents.orchestrator import Orchestrator
    orchestrator = Orchestrator()
    await orchestrator.run_report(period="noon")


async def close_report() -> None:
    """收盘报入口（供 GitHub Actions / run_job.py 调用）。"""
    from src.agents.orchestrator import Orchestrator
    orchestrator = Orchestrator()
    await orchestrator.run_report(period="close")
