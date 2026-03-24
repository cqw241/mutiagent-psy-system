export const DEFAULT_TYPEWRITER_FRAME_CHARS = 1
export const DEFAULT_TYPEWRITER_INTERVAL_MS = 36

export function chunkTextForTypewriter(
  text,
  frameChars = DEFAULT_TYPEWRITER_FRAME_CHARS,
) {
  const characters = Array.from(text ?? '')
  if (characters.length === 0) {
    return []
  }

  const normalizedFrameChars =
    Number.isFinite(frameChars) && frameChars > 0 ? Math.floor(frameChars) : 1

  const frames = []
  for (let index = 0; index < characters.length; index += normalizedFrameChars) {
    frames.push(characters.slice(index, index + normalizedFrameChars).join(''))
  }
  return frames
}

export function createTypewriterStream({
  onFrame,
  onIdle,
  frameChars = DEFAULT_TYPEWRITER_FRAME_CHARS,
  intervalMs = DEFAULT_TYPEWRITER_INTERVAL_MS,
  setTimer = (callback, delay) => globalThis.setTimeout(callback, delay),
  clearTimer = (timerId) => globalThis.clearTimeout(timerId),
} = {}) {
  let pendingFrames = []
  let timerId = null
  let disposed = false

  const clearScheduledFlush = () => {
    if (timerId === null) {
      return
    }

    clearTimer(timerId)
    timerId = null
  }

  const scheduleFlush = () => {
    if (disposed || timerId !== null || pendingFrames.length === 0) {
      return
    }

    timerId = setTimer(() => {
      timerId = null
      if (disposed) {
        return
      }

      const nextFrame = pendingFrames.shift()
      if (nextFrame) {
        onFrame?.(nextFrame)
      }

      if (pendingFrames.length > 0) {
        scheduleFlush()
        return
      }

      onIdle?.()
    }, intervalMs)
  }

  return {
    push(text) {
      if (disposed) {
        return
      }

      const frames = chunkTextForTypewriter(text, frameChars)
      if (frames.length === 0) {
        return
      }

      pendingFrames.push(...frames)
      scheduleFlush()
    },
    pendingText() {
      return pendingFrames.join('')
    },
    isIdle() {
      return pendingFrames.length === 0 && timerId === null
    },
    clear() {
      pendingFrames = []
      clearScheduledFlush()
    },
    dispose() {
      disposed = true
      pendingFrames = []
      clearScheduledFlush()
    },
  }
}
