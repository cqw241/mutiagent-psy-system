import assert from 'node:assert/strict'
import test from 'node:test'

import { chunkTextForTypewriter, createTypewriterStream } from './typewriterStream.js'

test('chunkTextForTypewriter splits incoming text into stable small frames', () => {
  assert.deepEqual(chunkTextForTypewriter('直接显示整段内容', 2), ['直接', '显示', '整段', '内容'])
  assert.deepEqual(chunkTextForTypewriter('abcdef', 3), ['abc', 'def'])
  assert.deepEqual(chunkTextForTypewriter('', 2), [])
})

test('createTypewriterStream emits queued text frame by frame', () => {
  const frames = []
  const scheduledCallbacks = []

  const stream = createTypewriterStream({
    frameChars: 2,
    intervalMs: 8,
    onFrame: (frame) => frames.push(frame),
    setTimer: (callback) => {
      scheduledCallbacks.push(callback)
      return scheduledCallbacks.length
    },
    clearTimer: () => {},
  })

  stream.push('abcdef')

  assert.equal(stream.isIdle(), false)
  assert.equal(stream.pendingText(), 'abcdef')

  while (scheduledCallbacks.length > 0) {
    const callback = scheduledCallbacks.shift()
    callback()
  }

  assert.deepEqual(frames, ['ab', 'cd', 'ef'])
  assert.equal(stream.pendingText(), '')
  assert.equal(stream.isIdle(), true)
})
