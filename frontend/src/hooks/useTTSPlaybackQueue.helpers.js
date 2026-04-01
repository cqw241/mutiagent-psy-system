const SILENT_WAV_DATA_URI =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA='
const PCM_SAMPLE_RATE = 24000
const PCM_CHANNELS = 1
const PCM_BITS_PER_SAMPLE = 16

function inferOutputFormat(mimeType) {
  if (mimeType === 'audio/mpeg') {
    return 'mp3'
  }
  if (mimeType === 'audio/wav') {
    return 'wav'
  }
  if (mimeType === 'audio/pcm') {
    return 'pcm'
  }
  return ''
}

function concatByteChunks(byteChunks) {
  const totalLength = byteChunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const joined = new Uint8Array(totalLength)
  let offset = 0

  for (const chunk of byteChunks) {
    joined.set(chunk, offset)
    offset += chunk.length
  }

  return joined
}

function writeAscii(view, offset, text) {
  for (let index = 0; index < text.length; index += 1) {
    view.setUint8(offset + index, text.charCodeAt(index))
  }
}

function wrapPcmChunksAsWav(byteChunks) {
  const pcmBytes = concatByteChunks(byteChunks)
  const headerSize = 44
  const wavBytes = new Uint8Array(headerSize + pcmBytes.length)
  const view = new DataView(wavBytes.buffer)
  const blockAlign = (PCM_CHANNELS * PCM_BITS_PER_SAMPLE) / 8
  const byteRate = PCM_SAMPLE_RATE * blockAlign

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + pcmBytes.length, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, PCM_CHANNELS, true)
  view.setUint32(24, PCM_SAMPLE_RATE, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, PCM_BITS_PER_SAMPLE, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, pcmBytes.length, true)
  wavBytes.set(pcmBytes, headerSize)

  return wavBytes
}

function normalizePlaybackSource({ byteChunks, mimeType, outputFormat }) {
  if (outputFormat !== 'pcm' && mimeType !== 'audio/pcm') {
    return { byteChunks, mimeType }
  }

  return {
    byteChunks: [wrapPcmChunksAsWav(byteChunks)],
    mimeType: 'audio/wav',
  }
}

export function createTTSSegmentCollector({
  graceMs = 120,
  onSegmentReady,
  schedule = (fn, delay) => setTimeout(fn, delay),
  cancel = (timer) => clearTimeout(timer),
} = {}) {
  const pendingSegments = new Map()

  function ensureEntry(segmentId, payload = {}) {
    const existing = pendingSegments.get(segmentId) ?? {
      segmentId,
      mimeType: payload.mime_type ?? 'audio/mpeg',
      outputFormat: payload.output_format ?? inferOutputFormat(payload.mime_type),
      sequence: payload.sequence ?? Number.MAX_SAFE_INTEGER,
      chunks: [],
      ended: false,
      timer: null,
    }

    existing.mimeType = payload.mime_type ?? existing.mimeType
    existing.outputFormat =
      payload.output_format ?? existing.outputFormat ?? inferOutputFormat(existing.mimeType)
    existing.sequence = payload.sequence ?? existing.sequence
    pendingSegments.set(segmentId, existing)
    return existing
  }

  function scheduleFinalize(segmentId) {
    const entry = pendingSegments.get(segmentId)
    if (!entry || !entry.ended) {
      return
    }

    if (entry.timer) {
      cancel(entry.timer)
    }

    entry.timer = schedule(() => {
      const latest = pendingSegments.get(segmentId)
      if (!latest || !latest.ended) {
        return
      }

      latest.timer = null

      if (!latest.chunks.length) {
        return
      }

      pendingSegments.delete(segmentId)
      onSegmentReady?.({
        segmentId: latest.segmentId,
        mimeType: latest.mimeType,
        outputFormat: latest.outputFormat,
        sequence: latest.sequence,
        chunks: [...latest.chunks],
      })
    }, graceMs)
  }

  return {
    handle(payload) {
      const segmentId = payload?.segment_id
      if (!segmentId) {
        return
      }

      if (payload.type === 'tts_audio') {
        const entry = ensureEntry(segmentId, payload)
        if (payload.payload) {
          entry.chunks.push(payload.payload)
        }
        if (entry.ended) {
          scheduleFinalize(segmentId)
        }
        return
      }

      if (payload.type === 'tts_end') {
        const entry = ensureEntry(segmentId, payload)
        entry.ended = true
        scheduleFinalize(segmentId)
      }
    },

    reset() {
      pendingSegments.forEach((entry) => {
        if (entry.timer) {
          cancel(entry.timer)
        }
      })
      pendingSegments.clear()
    },
  }
}

export function createUnlockedAudioPlayer({
  createHtmlAudio = () => new Audio(),
  createObjectURL = (blob) => URL.createObjectURL(blob),
  revokeObjectURL = (url) => URL.revokeObjectURL(url),
  BlobConstructor = Blob,
  silentSrc = SILENT_WAV_DATA_URI,
} = {}) {
  let audio = null
  let currentUrl = null
  let isPrimed = false

  function ensureAudio() {
    if (!audio) {
      audio = createHtmlAudio()
    }
    return audio
  }

  function clearCurrentUrl() {
    if (!currentUrl) {
      return
    }
    revokeObjectURL(currentUrl)
    currentUrl = null
  }

  function resetAudioElement() {
    if (!audio) {
      return
    }

    audio.pause?.()
    audio.onended = null
    audio.onerror = null
    try {
      audio.currentTime = 0
    } catch {}
  }

  return {
    async prime() {
      const player = ensureAudio()
      player.muted = true
      player.src = silentSrc
      player.load?.()

      try {
        await player.play?.()
        player.pause?.()
        try {
          player.currentTime = 0
        } catch {}
        player.muted = false
        isPrimed = true
        return true
      } catch {
        player.muted = false
        isPrimed = false
        return false
      }
    },

    async play({ byteChunks, mimeType, outputFormat, onEnded, onError } = {}) {
      const player = ensureAudio()
      const playbackSource = normalizePlaybackSource({ byteChunks, mimeType, outputFormat })
      const blob = new BlobConstructor(playbackSource.byteChunks, { type: playbackSource.mimeType })

      resetAudioElement()
      clearCurrentUrl()

      currentUrl = createObjectURL(blob)
      let finalized = false

      const finalize = () => {
        if (finalized) {
          return
        }
        finalized = true
        player.onended = null
        player.onerror = null
        clearCurrentUrl()
        onEnded?.()
      }

      player.onended = finalize
      player.onerror = () => {
        onError?.(new Error('audio-playback-error'))
        finalize()
      }
      player.muted = false
      player.src = currentUrl
      player.load?.()

      try {
        await player.play?.()
      } catch (error) {
        if (!isPrimed) {
          onError?.(error)
        } else {
          onError?.(error)
        }
        finalize()
      }

      return 'html-audio'
    },

    reset() {
      resetAudioElement()
      clearCurrentUrl()
    },

    async dispose() {
      this.reset()
      audio = null
      isPrimed = false
    },
  }
}
