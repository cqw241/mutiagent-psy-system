"""风险评估节点。

设计原则：
1. LLM 可以参与判断，但不能成为唯一风控依据
2. 高风险词命中时必须有规则兜底
3. 输出要同时包含离散风险等级和数值化风险分数
"""

from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings
from app.services.acoustic_fusion_service import (
    calibrate_risk_score,
    extract_acoustic_observations,
    summarize_acoustic_support,
)
from app.services.llm_client import BaseLLMClient, LiteLLMClient
from app.utils.state_helpers import latest_user_message, merge_agent_judgment

HIGH_RISK_KEYWORDS = ["不想活了", "自杀", "结束生命", "活不下去", "轻生"]
MEDIUM_RISK_KEYWORDS = ["崩溃", "绝望", "失眠", "痛苦", "焦虑"]
HIGH_RISK_BLACKLIST = [
    "不想活了",
    "想死",
    "自杀",
    "结束生命",
    "割腕",
    "跳楼",
    "吃安眠药",
    "吞药",
    "活着没意思",
    "寻短见",
    "寻死",
    "遗书",
    "伤害自己",
]
HIGH_RISK_VARIATION_PATTERNS = [
    re.compile(r"不想(?:再)?活(?:了|下去)?"),
    re.compile(r"(?:想|要)死"),
    re.compile(r"自杀"),
    re.compile(r"结束(?:自己的)?生命"),
    re.compile(r"割腕"),
    re.compile(r"跳楼"),
    re.compile(r"(?:吃安眠药|吞药|吞下?药片|药吃多了)"),
    re.compile(r"活着(?:没有|没)意思"),
    re.compile(r"寻短见|寻死"),
    re.compile(r"写?遗书"),
    re.compile(r"(?:伤害|弄伤)自己"),
    re.compile(r"(?:想|要|准备).{0,4}解脱"),
    re.compile(r"解脱.{0,6}(?:自己|生命|活着)"),
]


def _compute_rule_risk(keywords: list[str], text: str) -> tuple[str, float]:
    joined = " ".join(keywords) + " " + text
    if any(keyword in joined for keyword in HIGH_RISK_KEYWORDS):
        return "high", 0.95
    if any(keyword in joined for keyword in MEDIUM_RISK_KEYWORDS):
        return "medium", 0.60
    return "low", 0.20


def _safe_float(value: Any, default: float) -> float:
    """安全解析浮点数。

    LLM 结构化输出最常见的问题之一就是类型漂移，例如返回 `"high"`、
    空字符串或 `None`。这里统一做安全兜底，避免把上游模型抖动放大成 500。
    """

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# _latest_user_message removed — now using utils.state_helpers.latest_user_message


def _matches_high_risk_blacklist(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if any(phrase in normalized for phrase in HIGH_RISK_BLACKLIST):
        return True
    return any(pattern.search(normalized) for pattern in HIGH_RISK_VARIATION_PATTERNS)


def _has_high_risk_evidence(keywords: list[str], text: str) -> bool:
    joined = " ".join(keywords) + " " + text
    return _matches_high_risk_blacklist(joined)


def _merge_medium_signal(rule_risk_level: str, llm_risk_level: Any) -> bool:
    return rule_risk_level == "medium" or llm_risk_level == "medium"


def risk_assessor_node(
    state: dict[str, Any], llm_client: BaseLLMClient | None = None
) -> dict[str, Any]:
    """根据提取信息判断风险等级。"""

    llm = llm_client or LiteLLMClient(get_settings())
    latest_text = latest_user_message(state)
    keywords = state.get("extracted_signals", {}).get("emotion_keywords", [])
    acoustic_observations = state.get("extracted_signals", {}).get(
        "acoustic_observations",
        extract_acoustic_observations(
            state.get("multimodal_features", {}).get("voice_acoustic_features", {})
        ),
    )
    acoustic_support_level = summarize_acoustic_support(acoustic_observations)
    reference_context = state.get("reference_context", "")

    if _matches_high_risk_blacklist(latest_text):
        judgment = {
            "used_llm": False,
            "rule_risk_level": "high",
            "final_risk_level": "high",
            "reason": "strict keyword blacklist matched",
            "acoustic_observations": acoustic_observations,
            "acoustic_support_level": acoustic_support_level,
            "reference_context_used": bool(reference_context),
        }
        return {
            "risk_level": "high",
            "current_risk_score": 0.95,
            "referral_required": True,
            "agent_judgments": merge_agent_judgment(state, "risk_assessor", judgment),
        }

    system_prompt = (
        "你是高校心理风险评估节点。请只评估用户当前这一轮输入，不要因为上一轮对话而延续高风险标签。"
        "只有在当前输入明确提到自杀、自残、结束生命、伤害自己，或极端暴力威胁时，才允许给出 high。"
        "失眠、心情不好、焦虑、想聊天、问音乐推荐、寻求舒缓建议，这些都不是 high。"
        "不要把一般性的考试压力、学业挫败、情绪化抱怨、和 AI 争论、说自己很笨、说复习不完，当成危机。"
        "负面示例：'我最近睡不着'、'快考试了我复习不完'、'有什么舒缓的音乐推荐？'、'我是不是太蠢了'、"
        "'我都说了快考试我复习不完了'，这些都不能标记为 high。"
        "正面示例：'我不想活了'、'我想死'、'我要跳楼'、'我准备吞药'、'我在写遗书'，这些才可以标记为 high。"
        "如果没有明确自伤/自杀/极端暴力表达，就只能输出 low 或 medium。"
        "语音声学特征只作为辅助观察量，例如停顿增多、speech_ratio 降低、能量波动异常；"
        "它们不能单独推导出情绪分类、医学判断或 high 风险。"
        "请基于文本和提取线索输出 risk_level、risk_score、reason，"
        "仅返回 JSON，risk_level 只能是 low/medium/high。\n"
        "<Reference_Cases>\n"
        f"{reference_context or '无检索结果'}\n"
        "</Reference_Cases>\n"
        "请结合这些检索到的历史相似案例和心理评估标准，对当前用户的状况进行风险打分。"
        "如果有矛盾，优先参考 RAG 提供的专业标准。"
    )
    user_prompt = (
        f"用户文本：{latest_text}\n"
        f"提取线索：{keywords}\n"
        f"声学观察项：{acoustic_observations or '无'}\n"
        f"声学支持强度：{acoustic_support_level}\n"
        f"参考上下文是否存在：{'是' if reference_context else '否'}"
    )
    llm_result = llm.complete_json(system_prompt, user_prompt)

    rule_risk_level, rule_risk_score = _compute_rule_risk(keywords, latest_text)
    llm_risk_level = llm_result.get("risk_level")
    llm_risk_score = _safe_float(
        llm_result.get("risk_score", rule_risk_score), rule_risk_score
    )
    llm_high_is_corroborated = (
        llm_risk_level == "high"
        and llm_risk_score >= 0.85
        and _has_high_risk_evidence(keywords, latest_text)
    )

    if rule_risk_level == "high":
        risk_level = "high"
        risk_score = max(rule_risk_score, llm_risk_score)
    elif llm_high_is_corroborated:
        risk_level = "high"
        risk_score = llm_risk_score
    elif llm_risk_level == "high":
        risk_level = rule_risk_level
        risk_score = rule_risk_score
    elif _merge_medium_signal(rule_risk_level, llm_risk_level):
        risk_level = "medium"
        risk_score = max(
            0.6 if rule_risk_level == "medium" else 0.0,
            llm_risk_score if llm_risk_level == "medium" else 0.0,
            rule_risk_score,
        )
    elif llm_risk_level == "low":
        risk_level = "low"
        risk_score = llm_risk_score
    else:
        risk_level = rule_risk_level
        risk_score = rule_risk_score

    calibration = calibrate_risk_score(
        base_score=risk_score,
        risk_level=risk_level,
        support_level=acoustic_support_level,
    )
    risk_score = calibration["adjusted_score"]
    referral_required = risk_level == "high"
    judgment = {
        "used_llm": bool(llm_result),
        "rule_risk_level": rule_risk_level,
        "final_risk_level": risk_level,
        "reason": llm_result.get("reason", "rule-based fallback"),
        "acoustic_observations": acoustic_observations,
        "acoustic_support_level": acoustic_support_level,
        "base_score": calibration["base_score"],
        "adjusted_score": calibration["adjusted_score"],
        "used_acoustic_adjustment": calibration["used_acoustic_adjustment"],
        "reference_context_used": bool(reference_context),
    }

    return {
        "risk_level": risk_level,
        "current_risk_score": risk_score,
        "referral_required": referral_required,
        "agent_judgments": merge_agent_judgment(state, "risk_assessor", judgment),
    }
