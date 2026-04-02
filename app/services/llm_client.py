"""模型访问适配层。

节点只依赖这里定义的接口，而不直接依赖 Qwen、OpenAI 或本地模型 SDK。
这样未来从阿里云百炼迁移到私有化部署时，只需要替换这里的实现。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from app.core.config import Settings

try:
    import litellm
    from litellm import completion
except ImportError:  # pragma: no cover - 测试环境未安装时走安全降级
    litellm = None
    completion = None

logger = logging.getLogger(__name__)
_BUFFERED_STREAM_EMIT_INTERVAL_SECONDS = 0.008


class BaseLLMClient(ABC):
    """统一模型接口。"""

    @abstractmethod
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """返回 JSON 结构。

        Task 1 只需要支持结构化节点输出，因此统一返回 dict 即可。
        """

    @abstractmethod
    async def stream_text(
        self, system_prompt: str, user_prompt: str, fallback_text: str
    ) -> AsyncIterator[str]:
        """按 token/chunk 流式返回文本。"""


class LiteLLMClient(BaseLLMClient):
    """默认的 LiteLLM 实现。

    使用 OpenAI-compatible 入参风格，既能接百炼，也能接本地 vLLM / LM Studio / one-api。
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if litellm is not None:
            litellm.set_verbose = self.settings.llm_verbose

    @staticmethod
    def _network_disabled_for_test() -> bool:
        """在 pytest 运行时强制关闭真实模型网络调用。

        本地 `.env` 可以包含真实密钥，但自动化测试必须保持离线、稳定、可复现。
        """

        return bool(os.getenv("PYTEST_CURRENT_TEST"))

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """调用模型并尽量解析 JSON。

        如果环境没有配置 key、网络不可用、LiteLLM 未安装或输出不是合法 JSON，
        统一退化为空结果，由上层节点用规则兜底，保证风控链路可运行。
        """

        if completion is None or self._network_disabled_for_test():
            return {}
        if not self.settings.llm_api_key:
            return {}

        try:
            response = completion(
                model=self.settings.llm_model,
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                timeout=self.settings.llm_timeout_seconds,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": self._prepare_user_prompt(user_prompt)},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                extra_body=self._build_extra_body(),
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            self._log_litellm_failure("complete_json", exc)
            return {}

    async def stream_text(
        self, system_prompt: str, user_prompt: str, fallback_text: str
    ) -> AsyncIterator[str]:
        """流式输出文本。

        LiteLLM 当前返回的是同步迭代包装器；这里在 async 上下文中直接消费它。
        如果模型不可用，则退化为逐字符输出 fallback 文本，保证前端仍有“打字感”。
        """

        if (
            completion is None
            or not self.settings.llm_api_key
            or self._network_disabled_for_test()
        ):
            for char in fallback_text:
                yield char
            return

        try:
            stream = completion(
                model=self.settings.llm_model,
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                timeout=self.settings.llm_timeout_seconds,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": self._prepare_user_prompt(user_prompt)},
                ],
                temperature=0.4,
                stream=True,
                extra_body=self._build_extra_body(),
            )
            emitted = False
            for chunk in stream:
                delta = getattr(chunk.choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    emitted = True
                    # Some providers may buffer and return large chunks.
                    # Split to char-level tokens and add a tiny async yield between tokens
                    # so browser UIs can render a visible streaming effect consistently.
                    tokens = list(str(content))
                    for index, token in enumerate(tokens):
                        yield token
                        if index < len(tokens) - 1:
                            await asyncio.sleep(_BUFFERED_STREAM_EMIT_INTERVAL_SECONDS)
            if not emitted:
                for char in fallback_text:
                    yield char
        except Exception as exc:
            self._log_litellm_failure("stream_text", exc)
            for char in fallback_text:
                yield char

    def _log_litellm_failure(self, operation: str, exc: Exception) -> None:
        status_code = getattr(exc, "status_code", None)
        logger.exception(
            "LiteLLM %s failed model=%s base_url=%s status=%s error=%s",
            operation,
            self.settings.llm_model,
            self.settings.llm_base_url,
            status_code,
            exc,
        )

    def _build_extra_body(self) -> dict[str, Any] | None:
        if self._should_disable_thinking():
            return {"enable_thinking": False}
        return None

    def _prepare_user_prompt(self, user_prompt: str) -> str:
        if self._should_disable_thinking() and not user_prompt.startswith("/no_think"):
            return f"/no_think\n{user_prompt}"
        return user_prompt

    def _should_disable_thinking(self) -> bool:
        model_name = self.settings.llm_model.lower()
        return "qwen" in model_name
