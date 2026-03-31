"""FaceSegment Pydantic 校验模型。

用于 WebSocket 入口处对前端发来的面部特征快照进行结构化校验。
前端每 1–1.5 秒发送一次滑动窗口聚合后的 AU 强度与情绪混合得分。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FaceSegment(BaseModel):
    """单个面部特征快照（前端 1–1.5s 滑动窗口聚合结果）。

    Attributes:
        timestamp_ms: 快照对应时间戳（毫秒）。
        action_units: FACS 动作单元强度，如 {"AU01": 0.72, "AU04": 0.81}。
        blend_scores: 情绪混合得分，如 {"happy": 0.12, "sad": 0.67}。
    """

    timestamp_ms: int = Field(..., description="快照时间戳（ms）")
    action_units: dict[str, float] = Field(
        default_factory=dict, description="FACS AU 强度 (0.0–1.0)"
    )
    blend_scores: dict[str, float] = Field(
        default_factory=dict, description="情绪混合得分 (0.0–1.0)"
    )
