"""兼容层：保留旧导入路径，实际实现已拆分到 system_prompts/prompt_builders。"""

from app.prompts.prompt_builders import (
    build_information_extractor_prompts,
    build_response_generator_system_prompt,
    build_response_generator_user_prompt,
    build_risk_assessor_prompts,
    build_text_analyzer_prompts,
    build_voice_analyzer_prompts,
)

__all__ = [
    "build_text_analyzer_prompts",
    "build_information_extractor_prompts",
    "build_voice_analyzer_prompts",
    "build_risk_assessor_prompts",
    "build_response_generator_system_prompt",
    "build_response_generator_user_prompt",
]
