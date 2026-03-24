# Task 3 Realtime And UI Design

## Goal

为心理风险辅助系统增加可感知的实时交互层：后端支持 WebSocket 阶段事件与 token 流输出，高风险时异步触发 webhook 闭环；前端新增一个温暖、柔和的 React 聊天骨架，完成文本实时通信和高风险转介卡片展示。

## Chosen Architecture

采用一条统一的 LangGraph 执行链，同时输出两类流：

- `updates`：节点完成时的状态更新，用于映射成前端无害阶段事件
- `custom`：由 `response_generator_node` 使用 `get_stream_writer()` 主动发出的 token 事件

WebSocket 路由负责把这两类内部流，转换成稳定的前端消息协议：

- `{"type":"stage","name":"received","message":"已收到你的消息"}`
- `{"type":"stage","name":"rag_retriever_done","message":"正在结合专业案例认真分析"}`
- `{"type":"token","chunk":"我"}`
- `{"type":"final","reply":"...", "referral_required": false, "hotline_card": null}`
- `{"type":"end"}`
- `{"type":"error","message":"..."}`

## Safety Design

- 绝不把 `current_risk_score` 或内部风险推理细节发送给前端
- 高风险场景下，不直接流式输出未经约束的 LLM 原文，而是流式输出安全模板
- Webhook 走异步 fire-and-forget，不阻塞对用户的回复

## Frontend Direction

视觉方向采用温暖、柔和、低压迫感的界面：

- 米白、灰绿、雾蓝、浅陶土为主
- 大圆角卡片和轻阴影
- 不使用红色告警框
- 高风险时用“温暖提示卡片”替代强警报式 UI

## Local Dev

- 后端：`uvicorn app.main:app --reload`
- 前端：Vite + React + Tailwind，默认 `http://localhost:5173`
- WebSocket：`ws://localhost:8000/ws/chat/{session_id}`
