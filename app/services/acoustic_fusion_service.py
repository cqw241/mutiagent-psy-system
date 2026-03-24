"""文本与声学特征的规则化融合辅助逻辑。

这里只输出中性观察项和有限的评分校准，不做诊断，也不允许单靠声学特征触发高风险。
"""

from __future__ import annotations

from typing import Any, Literal


SupportLevel = Literal["none", "mild", "notable"]


def extract_acoustic_observations(
    acoustic_features: dict[str, Any] | None,
) -> list[str]:
    if not acoustic_features:
        return []

    observations: list[str] = []
    pause_total_ms = float(acoustic_features.get("pause_total_ms", 0) or 0)
    pause_mean_ms = float(acoustic_features.get("pause_mean_ms", 0) or 0)
    pause_count = int(acoustic_features.get("pause_count", 0) or 0)
    speech_ratio = float(acoustic_features.get("speech_ratio", 0) or 0)
    voiced_duration_ms = float(acoustic_features.get("voiced_duration_ms", 0) or 0)
    energy_std = acoustic_features.get("energy_std")
    rms_std = acoustic_features.get("rms_std")

    if pause_total_ms >= 1800 or pause_count >= 4:
        observations.append("pause_total_ms_high")
    elif pause_total_ms >= 900 or pause_mean_ms >= 450:
        observations.append("pause_pattern_elevated")

    if voiced_duration_ms >= 1000 and 0 < speech_ratio <= 0.45:
        observations.append("speech_ratio_low")
    elif voiced_duration_ms >= 1000 and speech_ratio <= 0.58:
        observations.append("speech_ratio_slightly_low")

    if energy_std is not None and float(energy_std) <= 0.001:
        observations.append("energy_variability_low")
    elif rms_std is not None and float(rms_std) <= 0.008:
        observations.append("rms_variability_low")

    return observations


def summarize_acoustic_support(observations: list[str]) -> SupportLevel:
    if not observations:
        return "none"
    if len(observations) >= 2 or "pause_total_ms_high" in observations:
        return "notable"
    return "mild"


def calibrate_risk_score(
    base_score: float,
    risk_level: str,
    support_level: SupportLevel,
) -> dict[str, Any]:
    if support_level == "none":
        adjusted_score = round(base_score, 3)
        return {
            "base_score": round(base_score, 3),
            "adjusted_score": adjusted_score,
            "used_acoustic_adjustment": False,
            "risk_level": risk_level,
        }

    adjustment = {
        "low": {"mild": 0.05, "notable": 0.12},
        "medium": {"mild": 0.04, "notable": 0.08},
        "high": {"mild": 0.0, "notable": 0.0},
    }.get(risk_level, {"mild": 0.0, "notable": 0.0})[support_level]

    adjusted = base_score + adjustment
    if risk_level == "low":
        adjusted = min(adjusted, 0.35)
    elif risk_level == "medium":
        adjusted = min(max(adjusted, 0.6), 0.84)
    elif risk_level == "high":
        adjusted = min(max(adjusted, 0.85), 0.99)

    adjusted_score = round(adjusted, 3)
    return {
        "base_score": round(base_score, 3),
        "adjusted_score": adjusted_score,
        "used_acoustic_adjustment": adjusted_score != round(base_score, 3),
        "risk_level": risk_level,
    }
