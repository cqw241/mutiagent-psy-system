import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { buildWebSocketUrl, useAudioStream } from './useAudioStream'
import { useTTSPlaybackQueue } from './useTTSPlaybackQueue'
import {
    appendVoiceTranscriptMessage,
    completeAssistantTyping,
    finalizeAssistantMessages,
} from './useChatAgent.helpers'

function makeSessionId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID()
    }
    return `session-${Date.now()}`
}

const STAGE_COPY = {
    received: '我收到了你的消息，先陪你把这段感受安稳地放下。',
    information_extractor_done: '正在认真理解你的感受与情绪线索。',
    text_analyzer_done: '正在细看你刚才说到的重点。',
    voice_analyzer_done: '正在整理你语音里的节奏和停顿线索。',
    face_analyzer_done: '正在结合你本地表情特征做辅助观察。',
    signal_aggregator_done: '正在把文字、声音和表情线索汇总起来。',
    rag_retriever_done: '正在结合专业案例与规范建议进行参考。',
    risk_assessor_done: '正在谨慎整理最合适的支持方式。',
    response_generator_done: '正在把回应组织成更温和、清晰的话语。',
}

export function useChatAgent({
    responseAudio = false,
    callMode = 'standard',
} = {}) {
    const sessionId = useMemo(() => makeSessionId(), [])
    const textSocketRef = useRef(null)
    const handlePayloadRef = useRef(null)
    const tokenBufferRef = useRef('')
    const ttsPlayback = useTTSPlaybackQueue({ enabled: responseAudio })

    const [input, setInput] = useState('')
    const [messages, setMessages] = useState([
        {
            id: 'welcome',
            role: 'assistant',
            text: '你好，我会以温和、清晰的方式陪你梳理当下的感受。你可以打字，也可以按下语音按钮，把现在最想说的一件事讲出来。',
        },
    ])
    const [connectionState, setConnectionState] = useState('connecting')
    const [stageLabel, setStageLabel] = useState('正在建立安全连接...')
    const [latestTrace, setLatestTrace] = useState(null)

    const finalizeAssistantReplyNow = useCallback((finalPayload) => {
        const replyText = finalPayload.reply || tokenBufferRef.current || ''

        setMessages((current) => {
            return finalizeAssistantMessages(current, {
                currentStreamId: null,
                replyText,
                finalPayload,
            })
        })

        setLatestTrace(finalPayload.trace ?? null)
        tokenBufferRef.current = ''
    }, [])

    const handleRealtimePayload = useCallback((payload) => {
        if (payload.type === 'tts_audio' || payload.type === 'tts_end') {
            ttsPlayback.handleTTSEvent(payload)
            return
        }

        if (payload.type === 'transcript') {
            const transcriptText = typeof payload.text === 'string' ? payload.text.trim() : ''
            if (!transcriptText) {
                return
            }

            setMessages((current) => appendVoiceTranscriptMessage(current, transcriptText))
            setStageLabel('语音已完成转写，正在整理回应。')
            return
        }

        if (payload.type === 'stage') {
            setStageLabel(STAGE_COPY[payload.name] ?? payload.message ?? '系统正在温和处理这条消息。')
            return
        }

        if (payload.type === 'token' || payload.type === 'chunk') {
            const text = payload.chunk ?? payload.content ?? ''
            if (!text) return
            tokenBufferRef.current += text
            return
        }

        if (payload.type === 'final') {
            const replyText = payload.reply || tokenBufferRef.current || ''
            if (!replyText) {
                finalizeAssistantReplyNow(payload)
                return
            }

            finalizeAssistantReplyNow({
                ...payload,
                reply: replyText,
            })
            return
        }

        if (payload.type === 'end') {
            setStageLabel('这轮回应已经整理完成。')
            return
        }

        if (payload.type === 'error') {
            setStageLabel(payload.message ?? '连接出现波动，请稍后重试。')
        }
    }, [finalizeAssistantReplyNow, ttsPlayback])

    handlePayloadRef.current = handleRealtimePayload

    const voiceStream = useAudioStream({
        sessionId,
        onEvent: handleRealtimePayload,
        userProfile: {},
        multimodalFeatures: {
            response_audio: responseAudio,
            call_mode: callMode,
        },
    })

    // Stable send function for face_segment frames over the voice WS
    const voiceSendFn = useCallback((data) => {
        const socket = voiceStream._socketRef?.current
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(data)
        }
    }, [voiceStream._socketRef])

    useEffect(() => {
        if (!voiceStream.lastError) {
            return
        }

        setStageLabel(voiceStream.lastError)
    }, [voiceStream.lastError])

    useEffect(() => {
        const socket = new WebSocket(buildWebSocketUrl(`/ws/chat/${sessionId}`))
        textSocketRef.current = socket

        socket.addEventListener('open', () => {
            setConnectionState('connected')
            setStageLabel('连接已建立，你可以开始输入或说话。')
        })

        socket.addEventListener('close', () => {
            setConnectionState('closed')
            setStageLabel('文字连接已断开，请刷新页面后重试。')
        })

        socket.addEventListener('message', (event) => {
            handlePayloadRef.current?.(JSON.parse(event.data))
        })

        return () => {
            socket.close()
        }
    }, [sessionId])

    const handleSubmit = useCallback((event) => {
        if (event) {
            event.preventDefault()
        }
        const message = input.trim()
        if (!message || !textSocketRef.current || textSocketRef.current.readyState !== WebSocket.OPEN) {
            return
        }

        setMessages((current) => [
            ...current.map((item) => {
                if (!item.streaming && !item.typing) {
                    return item
                }

                return {
                    ...item,
                    streaming: false,
                    typing: false,
                }
            }),
            { id: `user-${Date.now()}`, role: 'user', text: message },
        ])
        setInput('')
        setStageLabel('已发送，正在认真接住你的表达。')
        tokenBufferRef.current = ''
        textSocketRef.current.send(
            JSON.stringify({
                message,
                multimodal_features: {
                    response_audio: responseAudio,
                    call_mode: callMode,
                },
                user_profile: {},
            }),
        )
    }, [callMode, input, responseAudio])

    const handleVoiceToggle = useCallback(() => {
        if (voiceStream.isRecording) {
            setStageLabel('语音输入已提交，正在等待识别。')
        } else {
            setStageLabel('请自然说话，系统会在检测到停顿后自动转写。')
        }
        voiceStream.toggleStreaming()
    }, [voiceStream])

    const handleAssistantTypingDone = useCallback((messageId) => {
        setMessages((current) => completeAssistantTyping(current, messageId))
    }, [])

    return {
        sessionId,
        messages,
        input,
        setInput,
        connectionState,
        stageLabel,
        setStageLabel,
        latestTrace,
        handleSubmit,
        handleVoiceToggle,
        handleAssistantTypingDone,
        voiceStream,
        voiceSendFn,
        ttsPlayback,
    }
}
