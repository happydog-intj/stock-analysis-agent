"""
全局配置：从环境变量 / .env 文件读取所有配置（pydantic-settings v2）。

字段名使用小写，pydantic-settings 会自动匹配大写环境变量。
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # 允许大写环境变量映射到小写字段
        case_sensitive=False,
    )

    # ── LLM 通用配置 ────────────────────────────────────
    llm_provider: str = Field(
        default="claude",
        description="LLM 提供商（claude/qwen/kimi/glm/minimax）",
    )
    llm_model: str = Field(default="", description="指定模型名，留空则使用各提供商默认模型")

    # ── Claude（Anthropic）──────────────────────────────
    claude_api_key: str = Field(default="", description="Anthropic Claude API Key")
    claude_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude 模型名称",
    )
    claude_max_tokens: int = Field(default=2048, description="Claude 单次最大 token 数")
    claude_batch_size: int = Field(default=10, description="每批分析的评论数量")

    # ── Qwen（通义千问 / 阿里云）────────────────────────
    qwen_api_key: str = Field(default="", description="阿里云 DashScope API Key")

    # ── Kimi（月之暗面）────────────────────────────────
    kimi_api_key: str = Field(default="", description="Moonshot Kimi API Key")

    # ── GLM（智谱 AI）──────────────────────────────────
    glm_api_key: str = Field(default="", description="智谱 GLM API Key")

    # ── MiniMax ────────────────────────────────────────
    minimax_api_key: str = Field(default="", description="MiniMax API Key")
    minimax_group_id: str = Field(default="", description="MiniMax Group ID")

    # ── 飞书 ───────────────────────────────────────────
    feishu_webhook: str = Field(default="", description="飞书机器人 Webhook URL")
    feishu_secret: str = Field(default="", description="飞书机器人签名密钥（可选）")

    # ── Reddit ─────────────────────────────────────────
    reddit_client_id: str = Field(default="", description="Reddit API Client ID")
    reddit_client_secret: str = Field(default="", description="Reddit API Client Secret")
    reddit_username: str = Field(default="", description="Reddit 账号用户名")
    reddit_password: str = Field(default="", description="Reddit 账号密码")
    reddit_user_agent: str = Field(
        default="stock-analysis-agent/1.0",
        description="Reddit API User-Agent",
    )
    reddit_subreddits: list[str] = Field(
        default=["HKStocks", "stocks", "investing", "StockMarket", "SecurityAnalysis"],
        description="要监控的 subreddit 列表",
    )
    reddit_keywords: list[str] = Field(
        default=[
            "Mobvista",
            "Mintegral",
            "汇量科技",
            "1860.HK",
            "1860 HK",
            "HK1860",
        ],
        description="Reddit 关键词过滤列表",
    )

    # ── 雪球 ───────────────────────────────────────────
    xueqiu_cookies: str = Field(
        default="",
        description="雪球登录 Cookie（JSON 字符串，用于 Playwright）",
    )

    # ── 富途 ───────────────────────────────────────────
    futu_host: str = Field(default="127.0.0.1", description="富途 OpenD 主机")
    futu_port: int = Field(default=11111, description="富途 OpenD 端口")

    # ── Tiger Broker ───────────────────────────────────
    tiger_tiger_id: str = Field(default="", description="Tiger Broker Tiger ID")
    tiger_private_key: str = Field(default="", description="Tiger Broker RSA 私钥")

    # ── 目标股票 ────────────────────────────────────────
    primary_ticker: str = Field(default="1860.HK", description="主要跟踪股票代码")
    all_tickers: list[str] = Field(
        default=["1860.HK", "APP", "U", "DV", "MGNI"],
        description="全部跟踪股票代码（含竞对）",
    )

    # ── 数据库（保留字段供未来使用，当前无状态模式下不使用）──
    db_url: str = Field(default="sqlite+aiosqlite:///:memory:", description="数据库连接 URL")
    db_pool_size: int = Field(default=5, description="连接池大小")
    db_max_overflow: int = Field(default=10, description="连接池最大溢出数")

    # ── 调度时区与时间 ──────────────────────────────────
    scheduler_timezone: str = Field(default="Asia/Hong_Kong", description="调度器时区")
    morning_report_time: str = Field(default="09:00", description="晨报触发时间（HH:MM）")
    noon_report_time: str = Field(default="12:00", description="午报触发时间（HH:MM）")
    close_report_time: str = Field(default="15:00", description="收盘报触发时间（HH:MM）")

    # ── 采集间隔（秒）──────────────────────────────────
    collect_interval_xueqiu: int = Field(default=300, description="雪球采集间隔（秒）")
    collect_interval_hkex: int = Field(default=600, description="港交所公告轮询间隔（秒）")

    # ── 日志 ───────────────────────────────────────────
    log_level: str = Field(default="INFO", description="日志级别")


settings = Settings()
