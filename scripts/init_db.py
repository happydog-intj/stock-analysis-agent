"""
数据库初始化脚本：执行 001_init.sql，创建所有表结构。
在 GitHub Actions 中每次运行前调用。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from config.settings import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SQL_FILE = Path(__file__).parent.parent / "src" / "db" / "migrations" / "001_init.sql"


async def init_db() -> None:
    # asyncpg 直接连接（不经 SQLAlchemy）
    dsn = settings.DB_URL.replace("postgresql+asyncpg://", "postgresql://")

    logger.info("连接数据库：%s", dsn.split("@")[-1])
    conn = await asyncpg.connect(dsn)
    try:
        sql = SQL_FILE.read_text(encoding="utf-8")
        await conn.execute(sql)
        logger.info("✅ 数据库初始化完成")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(init_db())
