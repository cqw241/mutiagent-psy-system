import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { buildWebSocketUrl, useAudioStream } from './useAudioStream'

function makeSessionId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID()
    }
    return `session-${Date.now()}`
}

const STAGE_COPY = {
    received: '我收到了你的消息，先陪你把这段感受安稳地放下。',
    information_extractor_done: '正在认真理解你的感受与情绪线索。',
    rag_retriever_done: '正在结合专业案例与规范建议进行参考。',
    risk_assessor_done: '正在谨慎整理最合适的支持方式。',
    response_generator_done: '正在把回应组织成更温和、清晰的话语。',
}

export function useChatAgent() {
    const sessionId = useMemo(() => makeSessionId(), [])
    const textSocketRef = useRef(null)
    const streamingIdRef = useRef(null)
    const handlePayloadRef = useRef(null)
    const pendingFinalPayloadRef = useRef(null)
    const tokenBufferRef = useRef('')

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

    const finalizePendingAssistantReply = useCallback(() => {
        const finalPayload = pendingFinalPayloadRef.current
        if (!finalPayload) {
            return
        }

        pendingFinalPayloadRef.current = null

        const replyText = finalPayload.reply || ''
        setMessages((current) => {
            const currentStreamId = streamingIdRef.current
            let found = false

            const next = current.map((item) => {
                if (currentStreamId && item.id === currentStreamId) {
                    found = true
                    return { ...item, streaming: false }
                }
                return item
            })

            if (!found && replyText) {
                next.push({
                    id: `assistant-final-${Date.now()}`,
                    role: 'assistant',
                    text: replyText,
                    streaming: false,
                })
            }

            if (finalPayload.referral_required && finalPayload.hotline_card) {
                next.push({
                    id: `support-${Date.now()}`,
                    role: 'support',
                    card: finalPayload.hotline_card,
                })
            }

            return next
        })

        setLatestTrace(finalPayload.trace ?? null)
        streamingIdRef.current = null
    }, [])

    const handleRealtimePayload = useCallback((payload) => {
        if (payload.type === 'transcript') {
            setMessages((current) => {
                const lastMessage = current[current.length - 1]
                if (lastMessage?.role === 'user' && lastMessage?.text === payload.text) {
                    return current
                }

                return [
                    ...current,
                    {
                        id: `voice-user-${Date.now()}`,
                        role: 'user',
                        text: payload.text,
                    },
                ]
            })
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
            const replyText = payload.reply || tokenBufferRef.current
            pendingFinalPayloadRef.current = { ...payload, reply: replyText }
            tokenBufferRef.current = ''

            if (replyText) {
                const nextId = `assistant-${Date.now()}`
                streamingIdRef.current = nextId
                setMessages((current) => [
                    ...current,
                    {
                        id: nextId,
                        role: 'assistant',
                        text: replyText,
                        streaming: true,
                    },
                ])
                return
            }

            finalizePendingAssistantReply()
            return
        }

        if (payload.type === 'end') {
            setStageLabel('这轮回应已经整理完成。')
            return
        }

        if (payload.type === 'error') {
            setStageLabel(payload.message ?? '连接出现波动，请稍后重试。')
        }
    }, [finalizePendingAssistantReply])

    handlePayloadRef.current = handleRealtimePayload

    const voiceStream = useAudioStream({
        sessionId,
        onEvent: handleRealtimePayload,
        userProfile: {},
        multimodalFeatures: {},
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
            ...current.map((item) => (item.streaming ? { ...item, streaming: false } : item)),
            { id: `user-${Date.now()}`, role: 'user', text: message },
        ])
        setInput('')
        setStageLabel('已发送，正在认真接住你的表达。')
        tokenBufferRef.current = ''
        pendingFinalPayloadRef.current = null
        streamingIdRef.current = null
        textSocketRef.current.send(
            JSON.stringify({
                message,
                multimodal_features: {},
                user_profile: {},
            }),
        )
    }, [input])

    const handleVoiceToggle = useCallback(() => {
        if (voiceStream.isRecording) {
            setStageLabel('语音输入已提交，正在等待识别。')
        } else {
            setStageLabel('请自然说话，系统会在检测到停顿后自动转写。')
        }
        voiceStream.toggleStreaming()
    }, [voiceStream])

    return {
        sessionId,
        messages,
        input,
        setInput,
        connectionState,
        stageLabel,
        latestTrace,
        handleSubmit,
        handleVoiceToggle,
        voiceStream,
        voiceSendFn,
        finalizePendingAssistantReply,
    }
}
