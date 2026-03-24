"""信息提取节点。

职责：
1. 整理用户最新一轮文本和多模态特征
2. 用 LLM 生成结构化情绪关键词
3. 如果模型不可用，使用轻量规则兜底
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.services.acoustic_fusion_service import extract_acoustic_observations
from app.services.llm_client import BaseLLMClient, LiteLLMClient

EMOTION_KEYWORDS = [
    "痛苦",
    "难受",
    "焦虑",
    "失眠",
    "绝望",
    "不想活了",
    "崩溃",
    "害怕",
]


def _latest_user_message(state: dict[str, Any]) -> str:
    for message in reversed(state.get("chat_history", [])):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _rule_extract_keywords(text: str) -> list[str]:
    return [keyword for keyword in EMOTION_KEYWORDS if keyword in text]


def information_extractor_node(
    state: dict[str, Any], llm_client: BaseLLMClient | None = None
) -> dict[str, Any]:
    """提取文本和多模态中的风险线索。

    节点返回“增量状态”即可，LangGraph 会把它 merge 回总状态。
    """

    llm = llm_client or LiteLLMClient(get_settings())
    latest_text = _latest_user_message(state)
    multimodal = state.get("multimodal_features", {})
    acoustic_features = multimodal.get("voice_acoustic_features", {})
    acoustic_observations = extract_acoustic_observations(acoustic_features)

    system_prompt = (
        "你是高校心理风险识别系统中的信息提取节点。"
        "请从用户文本与多模态线索中提取 emotion_keywords、sentiment、observations，"
        "仅返回 JSON。"
    )
    user_prompt = (
        f"用户文本：{latest_text}\n"
        f"多模态特征：{multimodal}\n"
        "返回字段：emotion_keywords(list[str])、sentiment(str)、observations(list[str])。"
    )
    llm_result = llm.complete_json(system_prompt, user_prompt)

    rule_keywords = _rule_extract_keywords(latest_text)
    extracted_signals = {
        "emotion_keywords": llm_result.get("emotion_keywords") or rule_keywords,
        "sentiment": llm_result.get("sentiment", "unknown"),
        "observations": llm_result.get("observations", []),
        "acoustic_observations": acoustic_observations,
        "multimodal_summary": multimodal,
    }

    agent_judgments = dict(state.get("agent_judgments", {}))
    agent_judgments["information_extractor"] = {
        "latest_text": latest_text,
        "used_llm": bool(llm_result),
        "acoustic_observations": acoustic_observations,
        "extracted_signals": extracted_signals,
    }

    return {
        "extracted_signals": extracted_signals,
        "agent_judgments": agent_judgments,
    }
