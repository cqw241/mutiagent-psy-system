"""回复生成节点。

职责：
1. 依据风险等级生成温和、有同理心的回复
2. 高风险场景下，在 referral_agent 的过渡话术基础上做最终包装
3. 低/中风险场景下，用 LLM 流式生成自然对话

设计变更（本次重构）：
- 转介相关逻辑（hotline_card、webhook 告警）已解耦到 referral_agent
- 本节点只负责回复生成，不再处理告警闭环
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.models.schemas import ChatMessage
from app.services.llm_client import BaseLLMClient, LiteLLMClient
from app.utils.state_helpers import latest_user_message, merge_agent_judgment
from langgraph.config import get_stream_writer


def _safe_stream_writer():
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _payload: None


async def _stream_text_to_writer(
    llm: BaseLLMClient,
    writer,
    system_prompt: str,
    user_prompt: str,
    fallback_text: str,
) -> str:
    parts: list[str] = []
    async for chunk in llm.stream_text(system_prompt, user_prompt, fallback_text):
        parts.append(chunk)
        writer({"type": "token", "chunk": chunk})
    return "".join(parts)


async def response_generator_node(
    state: dict[str, Any],
    llm_client: BaseLLMClient | None = None,
) -> dict[str, Any]:
    """生成最终回复。"""

    llm = llm_client or LiteLLMClient(get_settings())
    writer = _safe_stream_writer()

    risk_level = state.get("risk_level", "low")
    latest_text = latest_user_message(state)
    used_llm = False

    stream_system_prompt = (
        "你是高校心理支持对话中的回复生成节点。"
        "请直接输出自然、温和、简洁的中文纯文本回复。"
        "不要输出 JSON、Markdown、代码块、字段名或多余前缀。"
        "你的回复应当像真实对话，而不是结构化数据。"
        "语气应温暖、非评判性，像一位关心同学的学姐/学长。"
    )

    if risk_level == "high":
        # 高风险：referral_agent 已设置了温和过渡话术作为 reply
        # 这里直接流式输出该 reply（不再调用 LLM 生成）
        existing_reply = state.get("reply", "")
        if existing_reply:
            for char in existing_reply:
                writer({"type": "token", "chunk": char})
            reply = existing_reply
        else:
            # 兜底：referral_agent 未设置 reply 时，使用安全模板
            fallback = (
                "我注意到你现在可能正处在非常痛苦和危险的状态。请先不要独自承受，"
                "尽快联系你身边可信任的人、学校辅导员，或拨打心理援助热线寻求即时支持。"
            )
            for char in fallback:
                writer({"type": "token", "chunk": char})
            reply = fallback
    elif risk_level == "medium":
        used_llm = True
        user_prompt = (
            f"风险等级：{risk_level}\n"
            f"用户输入：{latest_text}\n"
            "请直接回复用户。"
        )
        reply = await _stream_text_to_writer(
            llm,
            writer,
            stream_system_prompt,
            user_prompt,
            "听起来你最近承受了不少压力。你愿意和我继续说说，最近最让你难受的事情是什么吗？",
        )
    else:
        used_llm = True
        user_prompt = (
            f"风险等级：{risk_level}\n"
            f"用户输入：{latest_text}\n"
            "请直接回复用户。"
        )
        reply = await _stream_text_to_writer(
            llm,
            writer,
            stream_system_prompt,
            user_prompt,
            "谢谢你愿意分享现在的感受。我会先陪你梳理一下，你最近最明显的情绪变化是什么？",
        )

    judgment = {
        "used_llm": used_llm,
        "risk_level": risk_level,
    }

    return {
        "reply": reply,
        "agent_judgments": merge_agent_judgment(
            state, "response_generator", judgment
        ),
        "chat_history": [ChatMessage(role="assistant", content=reply).model_dump()],
    }
