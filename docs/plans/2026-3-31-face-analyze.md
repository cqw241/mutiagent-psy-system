Plan: 引入端侧视频表情分析能力 (Edge AI + Backend JSON 聚合)
这是为高校心理风险系统引入安全、保护隐私的面部表情分析功能的实施计划。核心是不传输原始视频帧，只在前端提取特征（AUs、情绪概率），通过后端 Python 映射为可解释的观察项。

Steps

更新状态定义：在图状态中引入时序面部特征存放结构，对齐现有的语音片段设计 (parallel with step 2)。
升级 WebSocket 接收逻辑：在后端 WS 路由中支持解析前端发来的 face_segment 帧数据，并存入会话状态。
重构面部分析节点 (核心 Python 规则映射)：替换占位逻辑，统计面部动作单元 (FACS AUs) 和预置情绪的时序均值，利用阈值规则映射为自然语言表达（如“持续皱眉”），确保非强诊断性 (depends on 1 & 2)。
统一多模态聚合：更新聚合节点，确保新增的多模态面部观测点被纳入传给风险评估 Agent 的综合上下文中。
升级大模型提示词：调整风险评估节点的系统/用户提示词构建器，指引大模型正确理解由于 FACS AUs 转化而来的面部辅助线索 (depends on 3 & 4)。
前端集成面部识别 (Edge AI)：在 React 前端引入 Mediapipe (或其他轻量算子模型)，开启摄像头抽提特征并推送至 WebSocket (parallel with step 1-5)。
前端 Trace 可视化：更新侧边栏的 Trace 面板 UI，追加面部动作与情绪的时间轴展示。
Relevant files

state.py — 扩展 PsychologyGraphState，添加 face_segments 列表。
后端 WebSocket 路由 (如 ws_chat.py 或语音路由) — 解析并存放 face_segment 类型的数据。
face_analyzer.py — 重构分析逻辑，提取 state["face_segments"][-1] 甚至更长时间窗的特征；建立针对 FACS 动作单元（如设阈值 AU04 > 0.6）及置信度的 Python 映射规则，产出客观的 facial_observations。
signal_aggregator.py — 确认提取 face_signals 中的新结构并装入 extracted_signals 给下游使用。
prompt_builders.py — 确保评估节点的 Prompt 能合理渲染面部的观察信息，不引发过度解读风险。
frontend/src/... — 引入 @mediapipe/tasks-vision 的 FaceLandmarker 逻辑以支持提取及推送；更新 Trace 面板代码绘制时间序列图。
Verification

使用 mock 的含 FACS AU 的 JSON 通过本地 Python 脚本投递到后端的 /ws，验证端到端的图状态流转是否正常，Trace 日志是否打出预期的“持续皱眉”。
执行 pytest 测试网路拓扑：针对 test_nodes.py 或者 test_workflow.py 补充针对高阀值与低阈值的 FACS 断言测试。
启动前端验证端到端加载时间，展示控制台输出以及 Trace 面板是否有相关特征点渲染。
Decisions

隐私保护：本设计基于白皮书红线限制，严格规定不传输、不保存任何视频图像画面，所有视觉计算只通过浏览器在本地完成（Edge AI），推送到后端只带有非结构/脱敏数字标签。
校准因子定位：面部推断只提供上下文校正，无论产生多么“极度悲伤”的标签，都不会单独导致直接触发最高危险告警（防止单一模态误判），最终防线仍由多模态融合的 risk_assessor 决定。
Further Considerations

防抖与传输频率：前端在抽提特征时，由于逐帧发送（比如 30fps）会导致高网络和状态写入负担，我们是否在前端先进行一个 1~2 秒滑动窗口的平均池化（Average Pooling），即每隔 1-2 秒仅向上游推送最具显著代表性的均值或者顶峰值？（推荐：前端防抖处理）