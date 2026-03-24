# Pilot MVP Contract

## Purpose

本系统用于高校心理风险的早期识别辅助、温和回应和规范转介支持。
它不是医疗系统，不提供诊断结论，不输出治疗方案。

## Supported Inputs

- 文本输入：`/chat`
- 文本 WebSocket：`/ws/chat/{session_id}`
- 语音 WebSocket：`/ws/voice-chat/{session_id}`

所有请求都必须带 `session_id` 或在 WebSocket 路径中体现会话身份。

## Supported Outputs

- 温和、非诊断性的中文回复
- `risk_level`: `low | medium | high`
- `referral_required`
- `trace_id`
- `trace`
- 高风险时返回 `hotline_card`

## Safety Guarantees

- 高风险输入必须经过 `risk_assessor -> referral_agent -> response_generator`
- 高风险不会绕过转介链路
- 输出中不得包含医疗诊断或治疗方案
- 对外日志和告警负载必须执行敏感信息脱敏

## State And Persistence

- 开发/测试默认使用内存 checkpointer
- 试点环境至少要求持久化 checkpoint，当前仓库内置 `file` 后端
- `session_id` 是跨轮会话恢复的主键

## Non-Goals

- 不做临床诊断
- 不做 EMR / HIS 集成
- 不在当前阶段承诺真实人脸模型推理上线
