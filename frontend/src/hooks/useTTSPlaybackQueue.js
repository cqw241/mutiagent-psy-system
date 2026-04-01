import { useCallback, useEffect, useRef, useState } from 'react'

function decodeBase64Chunk(payload) {
  const binary = window.atob(payload)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

export function useTTSPlaybackQueue({ enabled = false } = {}) {
  const pendingSegmentsRef = useRef(new Map())
  const playbackQueueRef = useRef([])
  const currentAudioRef = useRef(null)
  const isPlayingRef = useRef(false)

  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackError, setPlaybackError] = useState('')

  const resetPlayback = useCallback(() => {
    playbackQueueRef.current.forEach((entry) => {
      URL.revokeObjectURL(entry.url)
    })
    playbackQueueRef.current = []
    pendingSegmentsRef.current.clear()

    const currentAudio = currentAudioRef.current
    if (currentAudio) {
      currentAudio.pause()
      URL.revokeObjectURL(currentAudio.src)
      currentAudioRef.current = null
    }

    isPlayingRef.current = false
    setIsPlaying(false)
    setPlaybackError('')
  }, [])

  const playNext = useCallback(() => {
    if (!enabled || isPlayingRef.current) {
      return
    }

    const nextEntry = playbackQueueRef.current.shift()
    if (!nextEntry) {
      isPlayingRef.current = false
      setIsPlaying(false)
      return
    }

    const audio = new Audio(nextEntry.url)
    currentAudioRef.current = audio
    isPlayingRef.current = true
    setIsPlaying(true)

    const finalizePlayback = () => {
      URL.revokeObjectURL(nextEntry.url)
      if (currentAudioRef.current === audio) {
        currentAudioRef.current = null
      }
      isPlayingRef.current = false
      setIsPlaying(false)
      playNext()
    }

    audio.addEventListener('ended', finalizePlayback, { once: true })
    audio.addEventListener(
      'error',
      () => {
        setPlaybackError('语音播放出现波动，后续语音将继续尝试。')
        finalizePlayback()
      },
      { once: true },
    )

    audio.play().catch(() => {
      setPlaybackError('浏览器拦截了自动播放，请再次点击进入视频通话后重试。')
      finalizePlayback()
    })
  }, [enabled])

  const handleTTSEvent = useCallback(
    (payload) => {
      if (!enabled) {
        return
      }

      if (payload.type === 'tts_audio') {
        const segmentId = payload.segment_id
        if (!segmentId || !payload.payload) {
          return
        }

        const existing = pendingSegmentsRef.current.get(segmentId) ?? {
          mimeType: payload.mime_type ?? 'audio/mpeg',
          chunks: [],
          sequence: payload.sequence ?? Number.MAX_SAFE_INTEGER,
        }

        existing.chunks.push(payload.payload)
        pendingSegmentsRef.current.set(segmentId, existing)
        return
      }

      if (payload.type !== 'tts_end') {
        return
      }

      const segmentId = payload.segment_id
      if (!segmentId) {
        return
      }

      const completed = pendingSegmentsRef.current.get(segmentId)
      pendingSegmentsRef.current.delete(segmentId)
      if (!completed || !completed.chunks.length) {
        return
      }

      const byteChunks = completed.chunks.map((item) => decodeBase64Chunk(item))
      const blob = new Blob(byteChunks, { type: completed.mimeType })
      const url = URL.createObjectURL(blob)

      playbackQueueRef.current.push({
        sequence: completed.sequence,
        url,
      })
      playbackQueueRef.current.sort((left, right) => left.sequence - right.sequence)
      playNext()
    },
    [enabled, playNext],
  )

  useEffect(() => {
    if (!enabled) {
      resetPlayback()
    }
  }, [enabled, resetPlayback])

  useEffect(() => resetPlayback, [resetPlayback])

  return {
    handleTTSEvent,
    isPlaying,
    playbackError,
    resetPlayback,
  }
}
