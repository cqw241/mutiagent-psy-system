"""文本分析 Agent 节点。

职责：
1. 整理用户最新一轮文本
2. 用 LLM 生成结构化情绪关键词与文本观察项
3. 模型不可用时使用轻量规则兜底
4. 纯文本信号提取，不处理声学/面部特征（各模态独立 Agent）
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.prompts import build_text_analyzer_prompts
from app.services.llm_client import BaseLLMClient, LiteLLMClient
from app.utils.state_helpers import latest_user_message, merge_agent_judgment

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


def _rule_extract_keywords(text: str) -> list[str]:
    return [keyword for keyword in EMOTION_KEYWORDS if keyword in text]


def text_analyzer_node(
    state: dict[str, Any], llm_client: BaseLLMClient | None = None
) -> dict[str, Any]:
    """提取文本中的风险线索。

    节点返回"增量状态"即可，LangGraph 会把它 merge 回总状态。
    """

    llm = llm_client or LiteLLMClient(get_settings())
    latest_text = latest_user_message(state)
    multimodal = state.get("multimodal_features", {})

    system_prompt, user_prompt = build_text_analyzer_prompts(
        latest_text,
        multimodal,
    )
    llm_result = llm.complete_json(system_prompt, user_prompt)

    rule_keywords = _rule_extract_keywords(latest_text)
    text_signals = {
        "emotion_keywords": llm_result.get("emotion_keywords") or rule_keywords,
        "sentiment": llm_result.get("sentiment", "unknown"),
        "observations": llm_result.get("observations", []),
        "multimodal_summary": multimodal,
    }

    judgment = {
        "latest_text": latest_text,
        "used_llm": bool(llm_result),
        "text_signals": text_signals,
    }

    return {
        "text_signals": text_signals,
        "agent_judgments": merge_agent_judgment(state, "text_analyzer", judgment),
    }
