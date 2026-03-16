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

    # ── LLM 通用配置 ────────────────────────────────────
    # 支持：claude / qwen / kimi / glm / minimax
    LLM_PROVIDER: str = Field(
        default="claude",
        description="LLM 提供商（claude/qwen/kimi/glm/minimax）",
    )
    LLM_MODEL: str = Field(
        default="",
        description="指定模型名，留空则使用各提供商默认模型",
    )

    # ── Claude（Anthropic）──────────────────────────────
    # 控制台：https://console.anthropic.com/
    # 默认模型：claude-3-5-sonnet-20241022
    CLAUDE_API_KEY: str = Field(default="", description="Anthropic Claude API Key")

    # ── Qwen（通义千问 / 阿里云）────────────────────────
    # 控制台：https://dashscope.console.aliyun.com/
    # 默认模型：qwen-plus  可选：qwen-max / qwen-turbo / qwen-long
    QWEN_API_KEY: str = Field(default="", description="阿里云 DashScope API Key")

    # ── Kimi（月之暗面）────────────────────────────────
    # 控制台：https://platform.moonshot.cn/
    # 默认模型：moonshot-v1-32k  可选：moonshot-v1-8k / moonshot-v1-128k
    KIMI_API_KEY: str = Field(default="", description="Moonshot Kimi API Key")

    # ── GLM（智谱 AI）──────────────────────────────────
    # 控制台：https://open.bigmodel.cn/
    # 默认模型：glm-4-plus  可选：glm-4 / glm-4-air / glm-4-flash
    GLM_API_KEY: str = Field(default="", description="智谱 GLM API Key")

    # ── MiniMax ────────────────────────────────────────
    # 控制台：https://platform.minimaxi.com/
    # 默认模型：abab6.5s-chat  可选：abab5.5-chat
    MINIMAX_API_KEY:  str = Field(default="", description="MiniMax API Key")
    MINIMAX_GROUP_ID: str = Field(default="", description="MiniMax Group ID")

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
