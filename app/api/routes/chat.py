"""聊天接口。

当前只暴露一个最小 `/chat` 路由，用于把前端输入交给 LangGraph 执行。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.graph.workflow import get_compiled_graph
from app.models.schemas import ChatRequest, ChatResponse
from app.services.trace_service import build_trace_payload
from app.utils.state_helpers import build_initial_state

router = APIRouter(tags=["chat"])
compiled_graph = get_compiled_graph()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    """接收消息并执行风险识别图。"""

    initial_state = build_initial_state(
        session_id=payload.session_id,
        message=payload.message,
        user_profile=payload.user_profile,
        multimodal_features=payload.multimodal_features,
    )
    result = await compiled_graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": payload.session_id}},
    )
    return ChatResponse(
        reply=result["reply"],
        risk_level=result["risk_level"],
        referral_required=result["referral_required"],
        agent_judgments=result.get("agent_judgments", {}),
        extracted_signals=result.get("extracted_signals", {}),
        trace_id=result["trace_id"],
        trace=build_trace_payload(result),
        hotline_card=result.get("hotline_card"),
        alert_status=result.get("alert_status", {}),
    )
