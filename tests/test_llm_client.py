import asyncio
import logging
from types import SimpleNamespace

import app.services.llm_client as llm_client_module
from app.core.config import Settings


class HelperLiteLLMClient(llm_client_module.LiteLLMClient):
    @staticmethod
    def _network_disabled_for_test() -> bool:
        return False


async def _collect_stream(client):
    return [
        chunk
        async for chunk in client.stream_text(
            "system prompt",
            "user prompt",
            "fallback text",
        )
    ]


def test_litellm_client_enables_verbose_logging(monkeypatch):
    fake_litellm = SimpleNamespace(set_verbose=False)
    monkeypatch.setattr(llm_client_module, "litellm", fake_litellm, raising=False)

    HelperLiteLLMClient(Settings(llm_api_key="demo-key", llm_verbose=True))

    assert fake_litellm.set_verbose is True


def test_stream_text_logs_underlying_litellm_error(monkeypatch, caplog):
    def fake_completion(**kwargs):
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(llm_client_module, "completion", fake_completion)
    monkeypatch.setattr(
        llm_client_module,
        "litellm",
        SimpleNamespace(set_verbose=False),
        raising=False,
    )

    client = HelperLiteLLMClient(Settings(llm_api_key="demo-key"))

    with caplog.at_level(logging.ERROR):
        chunks = asyncio.run(_collect_stream(client))

    assert "".join(chunks) == "fallback text"
    assert "429 rate limit" in caplog.text


def test_stream_text_disables_qwen_thinking_mode(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(llm_client_module, "completion", fake_completion)
    monkeypatch.setattr(
        llm_client_module,
        "litellm",
        SimpleNamespace(set_verbose=False),
        raising=False,
    )

    client = HelperLiteLLMClient(Settings(llm_api_key="demo-key", llm_model="openai/qwen3.5-plus"))

    asyncio.run(_collect_stream(client))

    assert captured["extra_body"] == {"enable_thinking": False}
    assert captured["messages"][1]["content"].startswith("/no_think")
