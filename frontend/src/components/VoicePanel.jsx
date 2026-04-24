import { MicIcon, WaveIcon } from './Icons'
import { motion as Motion, AnimatePresence } from 'framer-motion'

function formatVoiceState(connectionState, isRecording) {
    if (isRecording) {
        return '正在收音'
    }
    if (connectionState === 'connecting') {
        return '语音链路连接中'
    }
    if (connectionState === 'connected') {
        return '语音待命'
    }
    if (connectionState === 'closed') {
        return '语音链路已关闭'
    }
    return '语音未启动'
}

function VoiceLevelMeter({ level }) {
    return (
        <div className="flex h-10 items-end gap-1.5 rounded-full bg-[#f7efe4] px-3.5 py-2">
            {[0.2, 0.38, 0.56, 0.74, 0.92].map((threshold) => (
                <span
                    key={threshold}
                    className={`h-full w-1.5 rounded-full transition-all duration-150 ease-out ${level >= threshold ? 'bg-[#8ca49b]' : 'bg-[#d9cdbd]'
                        }`}
                    style={{ transform: `scaleY(${Math.max(0.2, level / threshold)})` }}
                />
            ))}
        </div>
    )
}

export default function VoicePanel({ voiceStream, handleVoiceToggle, ttsPlayback }) {
    const voiceStateLabel = formatVoiceState(voiceStream.connectionState, voiceStream.isRecording)
    const playbackStateLabel = voiceStream.isRecording
        ? '录音中'
        : (ttsPlayback?.isPlaying ? '语音回复播放中' : '语音回复待命')
    const playbackError = ttsPlayback?.playbackError ?? ''

    return (
        <div className="mb-4 grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <Motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                className="rounded-[30px] border border-[#e7dacc] bg-[linear-gradient(145deg,#fffaf4_0%,#f3ebdf_100%)] p-5 shadow-[0_16px_40px_rgba(130,111,88,0.08)]"
            >
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <p className="text-xs uppercase tracking-[0.32em] text-stone-400">Voice Channel</p>
                        <p className="mt-2 font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-2xl text-stone-800">
                            心声倾听
                        </p>
                        <p className="mt-1.5 text-sm leading-relaxed text-stone-500">
                            点击麦克风，随意讲讲现在的感受。系统会在停顿后自动转写并回应。
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={handleVoiceToggle}
                        disabled={!voiceStream.supported}
                        className={`relative flex h-16 w-16 shrink-0 items-center justify-center rounded-full text-white shadow-[0_14px_30px_rgba(125,99,77,0.18)] transition-all duration-300 hover:scale-105 active:scale-95 ${voiceStream.isRecording
                                ? 'bg-[#a2675f] hover:bg-[#91544d]'
                                : 'bg-[#8ca49b] hover:bg-[#7a968c]'
                            } ${!voiceStream.supported ? 'cursor-not-allowed opacity-50' : ''}`}
                        aria-label={voiceStream.isRecording ? '停止语音输入' : '开始语音输入'}
                    >
                        {voiceStream.isRecording && (
                            <span className="absolute inset-0 -z-10 animate-ping rounded-full bg-[#a2675f] opacity-40"></span>
                        )}
                        <MicIcon />
                    </button>
                </div>

                <div className="mt-5 flex items-center gap-3">
                    <div className="rounded-full bg-white/80 px-4 py-2 text-sm font-medium text-stone-600 transition-colors">
                        {voiceStateLabel}
                    </div>
                    <div className="rounded-full bg-[#eef3ea] px-4 py-2 text-sm font-medium text-[#6f8a80] transition-colors">
                        {playbackStateLabel}
                    </div>
                    <VoiceLevelMeter level={voiceStream.audioLevel} />
                </div>

                {playbackError ? (
                    <p className="mt-4 rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-700">
                        {playbackError}
                    </p>
                ) : null}
            </Motion.div>

            <Motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex flex-col rounded-[30px] border border-[#d9dcca] bg-[linear-gradient(145deg,#eef3ea_0%,#fbf7f1_100%)] p-5 shadow-[0_16px_40px_rgba(122,135,112,0.08)]"
            >
                <div className="flex items-center gap-2 text-stone-500">
                    <WaveIcon />
                    <p className="text-xs uppercase tracking-[0.28em]">Latest Transcript</p>
                </div>
                <div className="mt-4 flex-1 rounded-[24px] bg-white/60 p-4 text-[15px] leading-7 text-stone-700 shadow-inner backdrop-blur-sm">
                    <AnimatePresence mode="wait">
                        <Motion.p
                            key={voiceStream.liveTranscript || 'empty'}
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -5 }}
                            className="min-h-[84px]"
                        >
                            {voiceStream.liveTranscript || (
                                <span className="text-stone-400 italic">说完一句后，这里会出现本轮语音识别结果...</span>
                            )}
                        </Motion.p>
                    </AnimatePresence>
                </div>
            </Motion.div>
        </div>
    )
}
