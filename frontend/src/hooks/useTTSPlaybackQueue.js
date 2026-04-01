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

  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackError, setPlaybackError] = useState('')

  function getPlayer() {
    if (!playerRef.current) {
      playerRef.current = createUnlockedAudioPlayer()
    }
    return playerRef.current
  }

  function enqueueCompletedSegment(segment) {
    const byteChunks = segment.chunks.map((item) => decodeBase64Chunk(item))
    playbackQueueRef.current.push({
      sequence: segment.sequence,
      byteChunks,
      mimeType: segment.mimeType,
      outputFormat: segment.outputFormat,
    })
    playbackQueueRef.current.sort((left, right) => left.sequence - right.sequence)
    void playNextRef.current?.()
  }

  function getCollector() {
    if (!collectorRef.current) {
      collectorRef.current = createTTSSegmentCollector({
        onSegmentReady: enqueueCompletedSegment,
      })
    }
    return collectorRef.current
  }

  const playNextRef = useRef(null)

  const resetPlayback = useCallback(() => {
    playbackQueueRef.current = []
    getCollector().reset()
    getPlayer().reset()

    isPlayingRef.current = false
    setIsPlaying(false)
    setPlaybackError('')
  }, [])

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
      void playNext()
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
  }, [enabled])
  playNextRef.current = playNext

  const primePlayback = useCallback(async () => {
    setPlaybackError('')
    try {
      await getPlayer().prime()
    } catch {
      setPlaybackError('当前浏览器尚未允许语音播放，请再点一次麦克风后重试。')
    }
  }, [])

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
    [enabled],
  )

  useEffect(() => {
    if (!enabled) {
      resetPlayback()
    }
  }, [enabled, resetPlayback])

  useEffect(() => {
    return () => {
      resetPlayback()
      void getPlayer().dispose()
    }
  }, [resetPlayback])

  return {
    handleTTSEvent,
    isPlaying,
    playbackError,
    primePlayback,
    resetPlayback,
  }
}
