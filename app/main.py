"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.api.routes.ws_chat import router as ws_chat_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="高校学生心理风险早期识别与转介辅助的多智能体后端骨架。",
)
app.include_router(chat_router)
app.include_router(ws_chat_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """健康检查接口，便于本地联调确认服务已启动。"""

    return {"status": "ok"}
