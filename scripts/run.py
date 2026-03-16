"""
scripts/run.py — 主入口脚本

启动完整的股票分析 Agent 系统，包括：
  1. 初始化数据库（可选 --init-db）
  2. 启动 APScheduler 定时任务
  3. 维持事件循环运行

使用方法：
    python scripts/run.py             # 正常启动
    python scripts/run.py --init-db   # 初始化 DB 后启动
    python scripts/run.py --test-report morning  # 立即触发一次晨报（测试用）
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# 将项目根目录加入 sys.path（确保 src/ 和 config/ 可导入）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from src.db.database import close_db, init_db  # noqa: E402
from src.scheduler.jobs import create_scheduler  # noqa: E402

# 配置根日志
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run")


async def main(args: argparse.Namespace) -> None:
    """主协程入口。"""

    # 1. 初始化数据库
    if args.init_db:
        logger.info("初始化数据库...")
        await init_db()
        logger.info("数据库初始化完成")

    # 2. 立即触发测试报告
    if args.test_report:
        from src.agents.orchestrator import Orchestrator

        logger.info("触发测试报告: %s", args.test_report)
        orchestrator = Orchestrator()
        await orchestrator.run_report(period=args.test_report)
        await orchestrator.close()
        await close_db()
        return

    # 3. 启动调度器
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("🚀 股票分析 Agent 已启动，调度器运行中...")
    logger.info(
        "   晨报: %s | 午报: %s | 收盘报: %s (%s)",
        settings.morning_report_time,
        settings.noon_report_time,
        settings.close_report_time,
        settings.scheduler_timezone,
    )

    # 4. 等待中断信号
    stop_event = asyncio.Event()

    def _handle_signal(sig: int, _frame: object) -> None:
        logger.info("收到信号 %s，准备优雅退出...", sig)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    await stop_event.wait()

    # 5. 优雅关闭
    logger.info("正在关闭调度器...")
    scheduler.shutdown(wait=True)
    await close_db()
    logger.info("✅ 系统已安全退出")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="股票分析 Agent — 汇量科技 1860.HK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="启动前初始化/升级数据库表结构",
    )
    parser.add_argument(
        "--test-report",
        choices=["morning", "noon", "close"],
        default=None,
        help="立即触发指定报告（测试用，发送后退出）",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
