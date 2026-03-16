"""
主启动入口：启动 APScheduler，开始每日三次定时报告。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from src.scheduler.jobs import create_scheduler, morning_report

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main(run_now: bool = False) -> None:
    """启动主程序。

    Args:
        run_now: 若为 True，立即执行一次晨报（调试用）。
    """
    scheduler = create_scheduler()
    scheduler.start()

    logger.info("=" * 50)
    logger.info("StockAnalysisAgent 已启动")
    logger.info("目标标的：%s", settings.PRIMARY_TICKER)
    logger.info("时区：%s", settings.TIMEZONE)
    logger.info("已注册任务：")
    for job in scheduler.get_jobs():
        logger.info("  - %s (%s)", job.name, job.next_run_time)
    logger.info("=" * 50)

    if run_now:
        logger.info("--run-now 模式：立即执行一次晨报")
        await morning_report()

    try:
        await asyncio.Event().wait()   # 永久阻塞，等待定时任务触发
    except (KeyboardInterrupt, SystemExit):
        logger.info("收到退出信号，正在关闭...")
        scheduler.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stock Analysis Agent")
    parser.add_argument("--run-now", action="store_true", help="立即执行一次晨报（测试用）")
    args = parser.parse_args()

    asyncio.run(main(run_now=args.run_now))
