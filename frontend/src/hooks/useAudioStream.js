import { useEffect, useRef, useState } from 'react'

const TARGET_SAMPLE_RATE = 16000

function getAudioContextConstructor() {
  if (typeof window === 'undefined') {
    return null
  }

  return window.AudioContext || window.webkitAudioContext || null
}

export function buildWebSocketUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const override = import.meta.env.VITE_API_WS_BASE_URL?.replace(/\/$/, '')
  if (override) {
    return `${override}${normalizedPath}`
  }

  if (typeof window === 'undefined') {
    return `ws://localhost:8000${normalizedPath}`
  }

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const hostname = window.location.hostname || 'localhost'
  return `${protocol}://${hostname}:8000${normalizedPath}`
}

function downsampleBuffer(input, inputSampleRate, targetSampleRate = TARGET_SAMPLE_RATE) {
  if (!input.length) {
    return new Float32Array()
  }

  if (inputSampleRate === targetSampleRate) {
    return new Float32Array(input)
  }

  const sampleRateRatio = inputSampleRate / targetSampleRate
  const newLength = Math.round(input.length / sampleRateRatio)
  const output = new Float32Array(newLength)

  let outputIndex = 0
  let inputIndex = 0
  while (outputIndex < newLength) {
    const nextInputIndex = Math.round((outputIndex + 1) * sampleRateRatio)
    let total = 0
    let count = 0

    for (let index = inputIndex; index < nextInputIndex && index < input.length; index += 1) {
      total += input[index]
      count += 1
    }

    output[outputIndex] = count > 0 ? total / count : 0
    outputIndex += 1
    inputIndex = nextInputIndex
  }

  return output
}

function floatTo16BitPCM(floatBuffer) {
  const pcm = new Int16Array(floatBuffer.length)

  for (let index = 0; index < floatBuffer.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, floatBuffer[index]))
    pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }

  return pcm
}

function calculateLevel(samples) {
  if (!samples.length) {
    return 0
  }

  let total = 0
  for (let index = 0; index < samples.length; index += 1) {
    total += samples[index] * samples[index]
  }

  return Math.min(1, Math.sqrt(total / samples.length) * 3)
}

export function useAudioStream({
  sessionId,
  onEvent,
  userProfile = {},
  multimodalFeatures = {},
} = {}) {
  const socketRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const audioContextRef = useRef(null)
  const sourceNodeRef = useRef(null)
  const processorNodeRef = useRef(null)
  const sinkNodeRef = useRef(null)
  const onEventRef = useRef(onEvent)
  const payloadContextRef = useRef({
    userProfile,
    multimodalFeatures,
  })

  const [connectionState, setConnectionState] = useState('idle')
  const [isRecording, setIsRecording] = useState(false)
  const [liveTranscript, setLiveTranscript] = useState('')
  const [audioLevel, setAudioLevel] = useState(0)
  const [lastError, setLastError] = useState('')

  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  useEffect(() => {
    payloadContextRef.current = {
      userProfile,
      multimodalFeatures,
    }
  }, [multimodalFeatures, userProfile])

  useEffect(() => {
    return () => {
      shutdownAudioGraph()

      const socket = socketRef.current
      if (socket) {
        socket.close()
        socketRef.current = null
      }
    }
  }, [])

  function shutdownAudioGraph() {
    const processorNode = processorNodeRef.current
    if (processorNode) {
      processorNode.onaudioprocess = null
      processorNode.disconnect()
      processorNodeRef.current = null
    }

    const sourceNode = sourceNodeRef.current
    if (sourceNode) {
      sourceNode.disconnect()
      sourceNodeRef.current = null
    }

    const sinkNode = sinkNodeRef.current
    if (sinkNode) {
      sinkNode.disconnect()
      sinkNodeRef.current = null
    }

    const mediaStream = mediaStreamRef.current
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }

    const audioContext = audioContextRef.current
    if (audioContext) {
      audioContext.close().catch(() => {})
      audioContextRef.current = null
    }

    setAudioLevel(0)
  }

  async function ensureSocketConnection() {
    const existingSocket = socketRef.current
    if (existingSocket?.readyState === WebSocket.OPEN) {
      return existingSocket
    }

    if (existingSocket?.readyState === WebSocket.CONNECTING) {
      return new Promise((resolve, reject) => {
        const handleOpen = () => {
          existingSocket.removeEventListener('error', handleError)
          resolve(existingSocket)
        }

        const handleError = () => {
          existingSocket.removeEventListener('open', handleOpen)
          reject(new Error('voice socket connect failed'))
        }

        existingSocket.addEventListener('open', handleOpen, { once: true })
        existingSocket.addEventListener('error', handleError, { once: true })
      })
    }

    setConnectionState('connecting')
    setLastError('')

    const socket = new WebSocket(buildWebSocketUrl(`/ws/voice-chat/${sessionId}`))
    socket.binaryType = 'arraybuffer'
    socketRef.current = socket

    socket.addEventListener('open', () => {
      setConnectionState('connected')
    })

    socket.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data)
      if (payload.type === 'transcript') {
        setLiveTranscript(payload.text ?? '')
      }
      if (payload.type === 'error') {
        setLastError(payload.message ?? '语音连接异常，请稍后重试。')
      }
      onEventRef.current?.(payload)
    })

    socket.addEventListener('close', () => {
      socketRef.current = null
      setConnectionState((current) => (current === 'idle' ? current : 'closed'))
      setIsRecording(false)
      setAudioLevel(0)
    })

    socket.addEventListener('error', () => {
      setLastError('语音连接初始化失败，请检查后端服务。')
    })

    return new Promise((resolve, reject) => {
      socket.addEventListener('open', () => resolve(socket), { once: true })
      socket.addEventListener(
        'error',
        () => reject(new Error('voice socket open failed')),
        { once: true },
      )
    })
  }

  async function startStreaming() {
    if (isRecording) {
      return
    }

    const AudioContextConstructor = getAudioContextConstructor()
    if (!AudioContextConstructor || !navigator.mediaDevices?.getUserMedia) {
      setLastError('当前浏览器不支持语音采集。')
      return
    }

    try {
      const socket = await ensureSocketConnection()
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })

      const audioContext = new AudioContextConstructor()
      await audioContext.resume()

      const sourceNode = audioContext.createMediaStreamSource(mediaStream)
      const processorNode = audioContext.createScriptProcessor(4096, 1, 1)
      const sinkNode = audioContext.createGain()
      sinkNode.gain.value = 0

      processorNode.onaudioprocess = (event) => {
        const floatSamples = event.inputBuffer.getChannelData(0)
        const downsampled = downsampleBuffer(floatSamples, audioContext.sampleRate)
        if (!downsampled.length) {
          return
        }

        setAudioLevel(calculateLevel(downsampled))

        if (socket.readyState !== WebSocket.OPEN) {
          return
        }

        const pcm = floatTo16BitPCM(downsampled)
        socket.send(pcm.buffer)
      }

      sourceNode.connect(processorNode)
      processorNode.connect(sinkNode)
      sinkNode.connect(audioContext.destination)

      mediaStreamRef.current = mediaStream
      audioContextRef.current = audioContext
      sourceNodeRef.current = sourceNode
      processorNodeRef.current = processorNode
      sinkNodeRef.current = sinkNode

      setIsRecording(true)
      setConnectionState('connected')
      setLastError('')
    } catch (error) {
      shutdownAudioGraph()
      setIsRecording(false)
      setLastError(error instanceof Error ? error.message : '麦克风启动失败。')
    }
  }

  function stopStreaming() {
    if (!isRecording) {
      return
    }

    shutdownAudioGraph()
    setIsRecording(false)

    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      const { multimodalFeatures: currentFeatures, userProfile: currentProfile } = payloadContextRef.current
      socket.send(
        JSON.stringify({
          type: 'input_audio_buffer.commit',
          multimodal_features: {
            ...currentFeatures,
            input_mode: 'voice',
            sample_rate: TARGET_SAMPLE_RATE,
          },
          user_profile: currentProfile,
        }),
      )
    }
  }

  function toggleStreaming() {
    if (isRecording) {
      stopStreaming()
      return
    }

    startStreaming()
  }

  return {
    audioLevel,
    connectionState,
    isRecording,
    lastError,
    liveTranscript,
    startStreaming,
    stopStreaming,
    toggleStreaming,
    supported: Boolean(getAudioContextConstructor() && navigator.mediaDevices?.getUserMedia),
  }
}
