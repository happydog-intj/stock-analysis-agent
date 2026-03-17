"""
单次报告执行器：供 GitHub Actions 调用。
用法：python scripts/run_job.py [morning|noon|close]
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

JOBS = {
    "morning": "src.scheduler.jobs.morning_report",
    "noon": "src.scheduler.jobs.noon_report",
    "close": "src.scheduler.jobs.close_report",
}


async def main(period: str) -> None:
    if period not in JOBS:
        logger.error("未知的报告类型：%s（可选：%s）", period, ", ".join(JOBS))
        sys.exit(1)

    # 动态导入并执行对应任务
    module_path, func_name = JOBS[period].rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    job_fn = getattr(module, func_name)

    logger.info("▶ 开始执行 [%s] 报告任务...", period)
    await job_fn()
    logger.info("✅ [%s] 报告任务完成", period)


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "morning"
    asyncio.run(main(period))
