"""
全局配置：从 .env 文件读取所有敏感配置（pydantic-settings）。
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 数据库 ─────────────────────────────────────────
    DB_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/stock_agent",
        description="PostgreSQL 异步连接 URL",
    )
    DB_POOL_SIZE: int = 10

    # ── Redis ──────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis 连接 URL（用于缓存 & 增量 ID）",
    )

    # ── Claude API ─────────────────────────────────────
    CLAUDE_API_KEY: str = Field(default="", description="Anthropic Claude API Key")
    CLAUDE_MODEL:   str = "claude-3-5-sonnet-20241022"

    # ── 飞书 ───────────────────────────────────────────
    FEISHU_WEBHOOK: str = Field(default="", description="飞书机器人 Webhook URL")

    # ── Reddit ─────────────────────────────────────────
    REDDIT_CLIENT_ID:     str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USERNAME:      str = ""
    REDDIT_PASSWORD:      str = ""

    # ── 雪球 ───────────────────────────────────────────
    XUEQIU_COOKIES: str = Field(
        default="",
        description="雪球登录 Cookie（JSON 字符串，用于 Playwright）",
    )

    # ── 富途 ───────────────────────────────────────────
    FUTU_HOST: str  = "127.0.0.1"
    FUTU_PORT: int  = 11111

    # ── 目标股票 ────────────────────────────────────────
    PRIMARY_TICKER: str = "1860.HK"

    # ── 调度时区 ────────────────────────────────────────
    TIMEZONE: str = "Asia/Hong_Kong"

    # ── 日志 ───────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


settings = Settings()
