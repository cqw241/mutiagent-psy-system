/**
 * useFaceAnalysis — Edge-AI 面部分析 React Hook
 *
 * 使用 @mediapipe/tasks-vision FaceLandmarker 在浏览器本地提取面部特征，
 * 通过 1.25 秒滑动窗口进行平均池化后再向 WebSocket 发送聚合结果。
 *
 * 隐私保证：原始视频帧永远不离开浏览器。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

const WASM_CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm'
const MODEL_PATH = '/models/face_landmarker.task'

/** 滑动窗口发射间隔（毫秒） */
const EMIT_INTERVAL_MS = 1250

/**
 * MediaPipe blendshape 名称 → 后端 AU 编码映射
 * 参考: https://developers.google.com/mediapipe/solutions/vision/face_landmarker/index#models
 */
const BLENDSHAPE_TO_AU = {
  browInnerUp: 'AU01',
  browOuterUpLeft: 'AU02',
  browOuterUpRight: 'AU02',
  browDownLeft: 'AU04',
  browDownRight: 'AU04',
  eyeWideLeft: 'AU05',
  eyeWideRight: 'AU05',
  cheekSquintLeft: 'AU06',
  cheekSquintRight: 'AU06',
  eyeSquintLeft: 'AU07',
  eyeSquintRight: 'AU07',
  noseSneerLeft: 'AU09',
  noseSneerRight: 'AU09',
  mouthUpperUpLeft: 'AU10',
  mouthUpperUpRight: 'AU10',
  mouthSmileLeft: 'AU12',
  mouthSmileRight: 'AU12',
  mouthFrownLeft: 'AU15',
  mouthFrownRight: 'AU15',
  mouthLowerDownLeft: 'AU17',
  mouthLowerDownRight: 'AU17',
  mouthStretchLeft: 'AU20',
  mouthStretchRight: 'AU20',
  mouthPressLeft: 'AU23',
  mouthPressRight: 'AU23',
  mouthOpen: 'AU25',
  jawOpen: 'AU26',
  mouthRollLower: 'AU28',
  mouthRollUpper: 'AU28',
  eyeBlinkLeft: 'AU45',
  eyeBlinkRight: 'AU45',
}

/** 简易情绪混合推断规则（从 AU 组合推断 blend_scores） */
function inferBlendScores(aus) {
  const scores = {}
  const smile = Math.max(aus.AU12 || 0, aus.AU06 || 0)
  if (smile > 0.3) scores.happy = smile
  const frown = Math.max(aus.AU15 || 0, aus.AU04 || 0, aus.AU01 || 0)
  if (frown > 0.3) scores.sad = frown
  const surprise = Math.max(aus.AU05 || 0, aus.AU26 || 0, aus.AU02 || 0)
  if (surprise > 0.3) scores.surprised = surprise
  const angry = Math.max(aus.AU04 || 0, aus.AU07 || 0, aus.AU23 || 0)
  if (angry > 0.3) scores.angry = angry
  const neutral = 1.0 - Math.max(smile, frown, surprise, angry, 0)
  if (neutral > 0) scores.neutral = Math.max(0, neutral)
  return scores
}

/**
 * 将 MediaPipe blendshape 数组转为 {AU_code: max_value} 字典
 */
function blendshapesToAUs(blendshapes) {
  const aus = {}
  for (const bs of blendshapes) {
    const auCode = BLENDSHAPE_TO_AU[bs.categoryName]
    if (auCode) {
      aus[auCode] = Math.max(aus[auCode] || 0, bs.score)
    }
  }
  return aus
}

/**
 * 对缓冲区内的多帧 AU 数据做平均池化
 */
function averageBuffer(buffer) {
  if (!buffer.length) return { action_units: {}, blend_scores: {} }

  // 收集所有出现过的 AU key
  const allKeys = new Set()
  for (const frame of buffer) {
    for (const key of Object.keys(frame)) allKeys.add(key)
  }

  const avgAUs = {}
  for (const key of allKeys) {
    let sum = 0
    let count = 0
    for (const frame of buffer) {
      if (frame[key] !== undefined) {
        sum += frame[key]
        count += 1
      }
    }
    avgAUs[key] = count > 0 ? sum / count : 0
  }

  return {
    action_units: avgAUs,
    blend_scores: inferBlendScores(avgAUs),
  }
}

export function useFaceAnalysis({ sendFn, enabled = false } = {}) {
  const [isActive, setIsActive] = useState(false)
  const [isCameraReady, setIsCameraReady] = useState(false)
  const [cameraError, setCameraError] = useState('')
  const [latestBlendshapes, setLatestBlendshapes] = useState(null)

  const videoRef = useRef(null)
  const landmarkerRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const animFrameRef = useRef(null)
  const bufferRef = useRef([])
  const emitTimerRef = useRef(null)
  const sendFnRef = useRef(sendFn)
  const lastTimestampRef = useRef(-1)

  useEffect(() => {
    sendFnRef.current = sendFn
  }, [sendFn])

  const cleanup = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }
    if (emitTimerRef.current) {
      clearInterval(emitTimerRef.current)
      emitTimerRef.current = null
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop())
      mediaStreamRef.current = null
    }
    if (landmarkerRef.current) {
      landmarkerRef.current.close()
      landmarkerRef.current = null
    }
    bufferRef.current = []
    setIsCameraReady(false)
    setLatestBlendshapes(null)
    lastTimestampRef.current = -1
  }, [])

  // Cleanup on unmount
  useEffect(() => cleanup, [cleanup])

  const emitAggregatedSegment = useCallback(() => {
    const buffer = bufferRef.current
    if (!buffer.length) return

    const { action_units, blend_scores } = averageBuffer(buffer)
    bufferRef.current = []

    const payload = {
      type: 'face_segment',
      data: {
        timestamp_ms: Date.now(),
        action_units,
        blend_scores,
      },
    }

    try {
      sendFnRef.current?.(JSON.stringify(payload))
    } catch {
      // WS may be closed, swallow silently
    }
  }, [])

  const startDetectionLoop = useCallback(
    (video, landmarker) => {
      function detect() {
        if (!video || video.paused || video.ended || !landmarkerRef.current) {
          return
        }

        // Avoid processing the same frame twice
        const currentTime = video.currentTime
        if (currentTime !== lastTimestampRef.current) {
          lastTimestampRef.current = currentTime
          try {
            const result = landmarker.detectForVideo(video, performance.now())
            if (result?.faceLandmarks?.length > 0 && result.faceBlendshapes?.[0]) {
              const blendshapes = result.faceBlendshapes[0].categories
              const aus = blendshapesToAUs(blendshapes)
              bufferRef.current.push(aus)
              setLatestBlendshapes(aus)
            }
          } catch {
            // Detection can fail on some frames, safe to skip
          }
        }

        animFrameRef.current = requestAnimationFrame(detect)
      }

      animFrameRef.current = requestAnimationFrame(detect)

      // Set up periodic emission
      emitTimerRef.current = setInterval(emitAggregatedSegment, EMIT_INTERVAL_MS)
    },
    [emitAggregatedSegment],
  )

  const start = useCallback(async () => {
    if (isActive) return
    setCameraError('')

    try {
      // Dynamic import to avoid loading WASM on page load
      const { FaceLandmarker, FilesetResolver } = await import('@mediapipe/tasks-vision')

      const vision = await FilesetResolver.forVisionTasks(WASM_CDN)
      const landmarker = await FaceLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: MODEL_PATH,
          delegate: 'GPU',
        },
        runningMode: 'VIDEO',
        outputFaceBlendshapes: true,
        outputFacialTransformationMatrixes: false,
        numFaces: 1,
      })

      landmarkerRef.current = landmarker

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 320, height: 240, facingMode: 'user' },
        audio: false,
      })
      mediaStreamRef.current = stream

      const video = videoRef.current
      if (!video) {
        throw new Error('Video element not available')
      }

      video.srcObject = stream
      await video.play()

      setIsCameraReady(true)
      setIsActive(true)

      startDetectionLoop(video, landmarker)
    } catch (err) {
      cleanup()
      setIsActive(false)
      setCameraError(err instanceof Error ? err.message : '摄像头启动失败')
    }
  }, [isActive, startDetectionLoop, cleanup])

  const stop = useCallback(() => {
    // Emit any remaining buffer before stopping
    emitAggregatedSegment()
    cleanup()
    setIsActive(false)
  }, [emitAggregatedSegment, cleanup])

  const toggle = useCallback(() => {
    if (isActive) {
      stop()
    } else {
      start()
    }
  }, [isActive, start, stop])

  // Auto-start / auto-stop based on enabled prop
  useEffect(() => {
    if (enabled && !isActive) {
      start()
    } else if (!enabled && isActive) {
      stop()
    }
  }, [enabled]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    videoRef,
    isActive,
    isCameraReady,
    cameraError,
    latestBlendshapes,
    start,
    stop,
    toggle,
  }
}
