import { motion as Motion, AnimatePresence } from 'framer-motion'

import { buildRagRetrievalRows } from './TracePanel.helpers'

function formatEmotion2vecStatus(status) {
    if (status === 'ok') return '推理成功'
    if (status === 'unavailable') return '暂不可用'
    if (status === 'error') return '推理失败'
    if (status === 'disabled') return '已关闭'
    return status || '未知'
}

function TraceDebugPanel({ trace, open, onToggle }) {
    if (!trace) {
        return null
    }

    const latestSegment = trace.latest_voice_segment
    const observations = trace.acoustic_observations ?? []
    const calibration = trace.risk_calibration ?? {}
    const emotion2vec = trace.emotion2vec ?? {}
    const faceAnalysis = trace.face_analysis ?? {}
    const facialObservations = faceAnalysis.facial_observations ?? []
    const ragRetrievalRows = buildRagRetrievalRows(trace)

    return (
        <>
            <div className="mt-5 rounded-[28px] border border-white/40 bg-[linear-gradient(145deg,#fbf5ec_0%,#eef2ec_100%)] p-5 shadow-sm transition-all hover:shadow-md">
                <button
                    type="button"
                    onClick={onToggle}
                    className="group flex w-full items-center justify-between text-left"
                >
                    <div>
                        <p className="text-xs uppercase tracking-[0.32em] text-stone-400">Assistant Diary</p>
                        <p className="mt-2 font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-xl text-stone-800 transition-colors group-hover:text-amber-800">
                            思考轨迹
                        </p>
                    </div>
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/60 text-sm text-stone-500 transition-colors group-hover:bg-white">
                        {open ? '−' : '+'}
                    </span>
                </button>

                <AnimatePresence>
                    {open && (
                        <Motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                        >
                            <div className="mt-4 space-y-3 pt-2 text-sm leading-6 text-stone-600">
                                <div className="rounded-2xl bg-white/75 px-4 py-3 shadow-inner">
                                    <p className="flex justify-between"><span className="text-stone-400">音频片段:</span> <span className="font-mono">{latestSegment?.segment_id ?? 'N/A'}</span></p>
                                    <p className="flex justify-between"><span className="text-stone-400">有效时长:</span> <span className="font-mono">{latestSegment?.duration_ms ? `${latestSegment.duration_ms}ms` : 'N/A'}</span></p>
                                </div>
                                <div className="rounded-2xl bg-white/75 px-4 py-3 shadow-inner">
                                    <p className="flex justify-between"><span className="text-stone-400">支持等级:</span> <span className="font-medium text-amber-700">{trace.acoustic_support_level ?? 'none'}</span></p>
                                    <p className="flex justify-between"><span className="text-stone-400">风险校准:</span> <span>{calibration.base_score ?? 'N'} &rarr; {calibration.adjusted_score ?? 'N'}</span></p>
                                </div>
                                <div className="rounded-2xl bg-white/75 px-4 py-3 shadow-inner">
                                    <p className="mb-2 text-stone-400">emotion2vec 当前状态:</p>
                                    <div className="space-y-2">
                                        <p className="flex justify-between">
                                            <span className="text-stone-400">状态:</span>
                                            <span className={`font-medium ${emotion2vec.status === 'ok' ? 'text-emerald-700' : emotion2vec.status === 'error' ? 'text-rose-700' : 'text-amber-700'}`}>
                                                {formatEmotion2vecStatus(emotion2vec.status)}
                                            </span>
                                        </p>
                                        <p className="flex justify-between">
                                            <span className="text-stone-400">是否生效:</span>
                                            <span>{emotion2vec.used ? '是' : '否'}</span>
                                        </p>
                                        <p className="flex justify-between">
                                            <span className="text-stone-400">标签:</span>
                                            <span className="font-mono">{emotion2vec.label ?? 'N/A'}</span>
                                        </p>
                                        <p className="flex justify-between">
                                            <span className="text-stone-400">置信度:</span>
                                            <span className="font-mono">
                                                {typeof emotion2vec.confidence === 'number' ? emotion2vec.confidence.toFixed(4) : 'N/A'}
                                            </span>
                                        </p>
                                        {emotion2vec.model_dir ? (
                                            <p className="break-all rounded-xl bg-stone-50 px-3 py-2 text-xs leading-5 text-stone-500">
                                                {emotion2vec.model_dir}
                                            </p>
                                        ) : null}
                                        {emotion2vec.error ? (
                                            <p className="rounded-xl border border-rose-100 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">
                                                {emotion2vec.error}
                                            </p>
                                        ) : null}
                                    </div>
                                </div>
                                <div className="rounded-2xl bg-white/75 px-4 py-3 shadow-inner">
                                    <p className="mb-2 text-stone-400">听觉特征与情绪线索:</p>
                                    <div className="flex flex-wrap gap-2">
                                        {observations.length > 0 ? (
                                            observations.map((item) => (
                                                <span key={item} className="rounded-full border border-[#e8dccb] bg-[#fdfaf5] px-3 py-1 text-xs text-stone-600">
                                                    {item}
                                                </span>
                                            ))
                                        ) : (
                                            <span className="text-stone-400 italic">未收到明显异常线索</span>
                                        )}
                                    </div>
                                </div>

                                <div className="rounded-2xl bg-white/75 px-4 py-3 shadow-inner">
                                    <p className="mb-2 text-stone-400">面部观察线索:</p>
                                    <div className="flex flex-wrap gap-2">
                                        {facialObservations.length > 0 ? (
                                            facialObservations.map((item) => (
                                                <span key={item} className="rounded-full border border-[#d6c8e2] bg-[#f8f4fc] px-3 py-1 text-xs text-purple-700">
                                                    {item}
                                                </span>
                                            ))
                                        ) : (
                                            <span className="text-stone-400 italic">未收到面部特征数据</span>
                                        )}
                                    </div>
                                    {faceAnalysis.dominant_blend && faceAnalysis.dominant_blend !== 'unknown' && (
                                        <div className="mt-3 space-y-1">
                                            <p className="flex justify-between">
                                                <span className="text-stone-400">主导表情:</span>
                                                <span className="font-mono text-purple-700">{faceAnalysis.dominant_blend}</span>
                                            </p>
                                            <p className="flex justify-between">
                                                <span className="text-stone-400">置信度:</span>
                                                <span className="font-mono">
                                                    {typeof faceAnalysis.dominant_confidence === 'number' ? faceAnalysis.dominant_confidence.toFixed(4) : 'N/A'}
                                                </span>
                                            </p>
                                            <p className="flex justify-between">
                                                <span className="text-stone-400">面部片段数:</span>
                                                <span className="font-mono">{faceAnalysis.segment_count ?? 0}</span>
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </Motion.div>
                    )}
                </AnimatePresence>
            </div>

            <div className="mt-4 rounded-[28px] border border-[#e1ece5] bg-[linear-gradient(145deg,#f8faf5_0%,#eef5ef_100%)] p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.32em] text-stone-400">Retrieval</p>
                <p className="mt-2 font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-xl text-stone-800">
                    RAG 检索状态
                </p>
                <div className="mt-4 space-y-2 text-sm">
                    {ragRetrievalRows.map((row) => (
                        <div key={row.key} className="flex items-center justify-between rounded-2xl bg-white/75 px-4 py-3 shadow-inner">
                            <span className="text-stone-500">{row.label}</span>
                            <span
                                className={`rounded-full px-3 py-1 text-xs font-medium ${
                                    row.tone === 'hit'
                                        ? 'bg-emerald-50 text-emerald-700'
                                        : row.tone === 'miss'
                                            ? 'bg-amber-50 text-amber-700'
                                            : row.tone === 'disabled'
                                                ? 'bg-stone-100 text-stone-500'
                                                : 'bg-sky-50 text-sky-700'
                                }`}
                            >
                                {row.status}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </>
    )
}

export default function TracePanel({ sessionId, latestTrace, isTraceOpen, setIsTraceOpen }) {
    return (
        <aside className="rounded-[34px] border border-white/70 bg-white/72 p-5 shadow-[0_20px_70px_rgba(118,99,79,0.10)] backdrop-blur">
            <div className="rounded-[28px] border border-white/50 bg-[linear-gradient(145deg,#fbf5ec_0%,#eef2ec_100%)] p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.32em] text-stone-400">Session ID</p>
                <p className="mt-3 break-all rounded-2xl bg-white/75 px-4 py-3 font-mono text-sm text-stone-500 shadow-inner">
                    {sessionId}
                </p>
            </div>

            <div className="mt-5 rounded-[28px] border border-[#f1e6d6] bg-[#f6efe5] p-5 shadow-sm">
                <p className="font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-xl text-stone-800">环境认知</p>
                <ul className="mt-4 space-y-3 text-sm leading-relaxed text-stone-600">
                    <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#8ca49b]"></span>
                        <span>语音链路使用独立 WebSocket，浏览器端 16kHz PCM 将直接送入后端 ASR 分析与特征提取。</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#8ca49b]"></span>
                        <span>面部特征仅在浏览器本地提取（Edge AI），不传输任何视频画面，每 1.25 秒聚合一次推送至后端。</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#8ca49b]"></span>
                        <span>由于网络波动可能存在短暂延迟，停止录音时会进行尾部缓冲补充。</span>
                    </li>
                </ul>
            </div>

            <TraceDebugPanel
                trace={latestTrace}
                open={isTraceOpen}
                onToggle={() => setIsTraceOpen((current) => !current)}
            />
        </aside>
    )
}
