import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createTTSSegmentCollector,
  createUnlockedAudioPlayer,
} from './useTTSPlaybackQueue.helpers'

function decodeBase64Chunk(payload) {
  const binary = window.atob(payload)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

export function useTTSPlaybackQueue({ enabled = false } = {}) {
  const playbackQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const playerRef = useRef(null)
  const collectorRef = useRef(null)
  const playNextRef = useRef(null)

  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackError, setPlaybackError] = useState('')

  const getPlayer = useCallback(() => {
    if (!playerRef.current) {
      playerRef.current = createUnlockedAudioPlayer()
    }
    return playerRef.current
  }, [])

  const enqueueCompletedSegment = useCallback((segment) => {
    const byteChunks = segment.chunks.map((item) => decodeBase64Chunk(item))
    playbackQueueRef.current.push({
      sequence: segment.sequence,
      byteChunks,
      mimeType: segment.mimeType,
      outputFormat: segment.outputFormat,
    })
    playbackQueueRef.current.sort((left, right) => left.sequence - right.sequence)
    void playNextRef.current?.()
  }, [])

  const getCollector = useCallback(() => {
    if (!collectorRef.current) {
      collectorRef.current = createTTSSegmentCollector({
        onSegmentReady: enqueueCompletedSegment,
      })
    }
    return collectorRef.current
  }, [enqueueCompletedSegment])

  const resetPlayback = useCallback(() => {
    playbackQueueRef.current = []
    getCollector().reset()
    getPlayer().reset()

    isPlayingRef.current = false
    setIsPlaying(false)
    setPlaybackError('')
  }, [getCollector, getPlayer])

  const playNext = useCallback(async () => {
    if (!enabled || isPlayingRef.current) {
      return
    }

    const nextEntry = playbackQueueRef.current.shift()
    if (!nextEntry) {
      isPlayingRef.current = false
      setIsPlaying(false)
      return
    }

    isPlayingRef.current = true
    setIsPlaying(true)

    const finalizePlayback = () => {
      isPlayingRef.current = false
      setIsPlaying(false)
      void playNextRef.current?.()
    }

    await getPlayer().play({
      byteChunks: nextEntry.byteChunks,
      mimeType: nextEntry.mimeType,
      outputFormat: nextEntry.outputFormat,
      onEnded: finalizePlayback,
      onError: () => {
        setPlaybackError('浏览器或设备拦截了语音播放，请再点一次麦克风后重试。')
      },
    }).catch(() => {
      setPlaybackError('语音播放出现波动，后续语音将继续尝试。')
      finalizePlayback()
    })
  }, [enabled, getPlayer])

  useEffect(() => {
    playNextRef.current = playNext
  }, [playNext])

  const primePlayback = useCallback(async () => {
    setPlaybackError('')
    try {
      await getPlayer().prime()
    } catch {
      setPlaybackError('当前浏览器尚未允许语音播放，请再点一次麦克风后重试。')
    }
  }, [getPlayer])

  const handleTTSEvent = useCallback(
    (payload) => {
      if (!enabled) {
        return
      }

      if (payload.type !== 'tts_audio' && payload.type !== 'tts_end') {
        return
      }
      getCollector().handle(payload)
    },
    [enabled, getCollector],
  )

  useEffect(() => {
    if (!enabled) {
      const timerId = window.setTimeout(resetPlayback, 0)
      return () => window.clearTimeout(timerId)
    }
  }, [enabled, resetPlayback])

  useEffect(() => {
    return () => {
      resetPlayback()
      void getPlayer().dispose()
    }
  }, [getPlayer, resetPlayback])

  return {
    handleTTSEvent,
    isPlaying,
    playbackError,
    primePlayback,
    resetPlayback,
  }
}
