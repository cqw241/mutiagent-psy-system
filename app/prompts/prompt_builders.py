"""集中存放各节点的 user prompt 构建器。"""

from __future__ import annotations

from typing import Any

from app.prompts.system_prompts import (
    INFORMATION_EXTRACTOR_SYSTEM_PROMPT,
    RESPONSE_GENERATOR_SYSTEM_PROMPT,
    RISK_ASSESSOR_SYSTEM_PROMPT_TEMPLATE,
    TEXT_ANALYZER_SYSTEM_PROMPT,
    VOICE_ANALYZER_SYSTEM_PROMPT,
)


def build_text_analyzer_prompts(
    latest_text: str,
    multimodal: dict[str, Any],
) -> tuple[str, str]:
    user_prompt = (
        f"用户文本：{latest_text}\n"
        f"多模态特征概览：{multimodal}\n"
        "返回字段：emotion_keywords(list[str])、sentiment(str)、observations(list[str])。"
    )
    return TEXT_ANALYZER_SYSTEM_PROMPT, user_prompt


def build_information_extractor_prompts(
    latest_text: str,
    multimodal: dict[str, Any],
) -> tuple[str, str]:
    user_prompt = (
        f"用户文本：{latest_text}\n"
        f"多模态特征：{multimodal}\n"
        "返回字段：emotion_keywords(list[str])、sentiment(str)、observations(list[str])。"
    )
    return INFORMATION_EXTRACTOR_SYSTEM_PROMPT, user_prompt


def build_voice_analyzer_prompts(
    features: dict[str, Any],
    user_text: str,
    emotion_heuristic: dict[str, Any],
) -> tuple[str, str]:
    user_prompt = (
        f"声学物理特征：{features.get('physical_features', {})}\n"
        f"MFCC 统计：n_mfcc={features.get('mfcc_features', {}).get('n_mfcc', 0)}, "
        f"帧数={features.get('mfcc_features', {}).get('n_frames', 0)}\n"
        f"启发式情绪推断：{emotion_heuristic}\n"
        f"用户文本（如有）：{user_text or '无文本输入'}\n"
        "请给出你的情绪观察。"
    )
    return VOICE_ANALYZER_SYSTEM_PROMPT, user_prompt


def build_risk_assessor_prompts(
    latest_text: str,
    keywords: list[str],
    acoustic_observations: list[str],
    acoustic_support_level: str,
    reference_context: str,
    facial_observations: list[str] | None = None,
) -> tuple[str, str]:
    system_prompt = RISK_ASSESSOR_SYSTEM_PROMPT_TEMPLATE.format(
        reference_context=reference_context or "无检索结果"
    )
    facial_block = "、".join(facial_observations) if facial_observations else "无"
    user_prompt = (
        f"用户文本：{latest_text}\n"
        f"提取线索：{keywords}\n"
        f"声学观察项：{acoustic_observations or '无'}\n"
        f"声学支持强度：{acoustic_support_level}\n"
        f"面部观察项（仅作上下文校准）：{facial_block}\n"
        f"参考上下文是否存在：{'是' if reference_context else '否'}"
    )
    return system_prompt, user_prompt


def build_response_generator_system_prompt(peer_support_context: str = "") -> str:
    base_prompt = RESPONSE_GENERATOR_SYSTEM_PROMPT
    if peer_support_context:
        base_prompt += (
            "\n\n<Peer_Support_Examples>\n"
            f"{peer_support_context}\n"
            "</Peer_Support_Examples>\n"
            "请将以上系统检索到的往期同辈优秀沟通样例作为风格对齐参照，"
            "用相似的同情心、验证感和非评判语气进行陪伴回复。"
        )
    return base_prompt


def build_response_generator_user_prompt(risk_level: str, latest_text: str) -> str:
    return (
        f"风险等级：{risk_level}\n"
        f"用户输入：{latest_text}\n"
        "请直接回复用户。"
    )
