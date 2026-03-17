"""
统一 LLM 客户端工厂：支持 Claude / Qwen / Kimi / GLM / MiniMax。
所有非 Claude 提供商均使用 OpenAI 兼容接口（openai SDK + 自定义 base_url）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

# ── 提供商默认模型 ──────────────────────────────────────────────
DEFAULT_MODELS: dict[str, str] = {
    "claude": "claude-3-5-sonnet-20241022",
    "qwen": "qwen-plus",
    "kimi": "moonshot-v1-32k",
    "glm": "glm-4-plus",
    "minimax": "abab6.5s-chat",
}

# ── OpenAI 兼容接口的 Base URL ──────────────────────────────────
OPENAI_COMPAT_URLS: dict[str, str] = {
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4/",
    "minimax": "https://api.minimax.chat/v1",
}


class BaseLLMClient(ABC):
    """LLM 客户端基类。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """发送对话请求，返回纯文本回复。"""
        ...

    @property
    @abstractmethod
    def provider(self) -> str: ...

    @property
    @abstractmethod
    def model(self) -> str: ...


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude 客户端。"""

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def provider(self) -> str:
        return "claude"

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
        )
        return resp.content[0].text.strip()


class OpenAICompatClient(BaseLLMClient):
    """通用 OpenAI 兼容客户端（Qwen / Kimi / GLM / MiniMax）。"""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        self._provider = provider
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=extra_headers or {},
        )

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()


# ── 工厂函数 ────────────────────────────────────────────────────


def create_llm_client() -> BaseLLMClient:
    """根据 settings.llm_provider 创建对应的 LLM 客户端。"""
    from config.settings import settings

    provider = settings.llm_provider.lower()
    model = settings.llm_model or DEFAULT_MODELS.get(provider, "")

    logger.info("LLM 提供商: %s | 模型: %s", provider, model)

    if provider == "claude":
        if not settings.CLAUDE_API_KEY:
            raise ValueError("CLAUDE_API_KEY 未配置")
        return ClaudeClient(api_key=settings.CLAUDE_API_KEY, model=model)

    if provider == "qwen":
        if not settings.QWEN_API_KEY:
            raise ValueError("QWEN_API_KEY 未配置")
        return OpenAICompatClient(
            provider="qwen",
            api_key=settings.QWEN_API_KEY,
            model=model,
            base_url=OPENAI_COMPAT_URLS["qwen"],
        )

    if provider == "kimi":
        if not settings.KIMI_API_KEY:
            raise ValueError("KIMI_API_KEY 未配置")
        return OpenAICompatClient(
            provider="kimi",
            api_key=settings.KIMI_API_KEY,
            model=model,
            base_url=OPENAI_COMPAT_URLS["kimi"],
        )

    if provider == "glm":
        if not settings.GLM_API_KEY:
            raise ValueError("GLM_API_KEY 未配置")
        return OpenAICompatClient(
            provider="glm",
            api_key=settings.GLM_API_KEY,
            model=model,
            base_url=OPENAI_COMPAT_URLS["glm"],
        )

    if provider == "minimax":
        if not settings.MINIMAX_API_KEY:
            raise ValueError("MINIMAX_API_KEY 未配置")
        return OpenAICompatClient(
            provider="minimax",
            api_key=settings.MINIMAX_API_KEY,
            model=model,
            base_url=OPENAI_COMPAT_URLS["minimax"],
            extra_headers={"Authorization": f"Bearer {settings.MINIMAX_API_KEY}"},
        )

    raise ValueError(f"不支持的 LLM 提供商：{provider}，可选：{', '.join(DEFAULT_MODELS.keys())}")
