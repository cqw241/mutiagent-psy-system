import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createTTSSegmentCollector,
  createUnlockedAudioPlayer,
} from './useTTSPlaybackQueue.helpers.js'

test('createUnlockedAudioPlayer reuses a primed html audio element for mp3 playback', async () => {
  let htmlAudioCreated = 0
  let playCalls = 0
  let pauseCalls = 0
  let endedCount = 0
  let lastSrc = ''

  const fakeAudio = {
    src: '',
    muted: false,
    currentTime: 0,
    addEventListener(eventName, handler) {
      this[`on${eventName}`] = handler
    },
    removeEventListener() {},
    async play() {
      playCalls += 1
      lastSrc = this.src
      if (this.src.startsWith('blob:')) {
        queueMicrotask(() => {
          this.onended?.()
        })
      }
    },
    pause() {
      pauseCalls += 1
    },
    load() {},
  }

  const player = createUnlockedAudioPlayer({
    createHtmlAudio: () => {
      htmlAudioCreated += 1
      return fakeAudio
    },
    createObjectURL: () => 'blob:reply-segment',
    revokeObjectURL: () => {},
  })

  assert.equal(await player.prime(), true)
  assert.equal(htmlAudioCreated, 1)

  await player.play({
    byteChunks: [new Uint8Array([1, 2, 3])],
    mimeType: 'audio/mpeg',
    onEnded: () => {
      endedCount += 1
    },
  })

  await new Promise((resolve) => setTimeout(resolve, 0))

  assert.equal(playCalls, 2)
  assert.equal(pauseCalls, 2)
  assert.equal(lastSrc, 'blob:reply-segment')
  assert.equal(endedCount, 1)
})

test('createUnlockedAudioPlayer falls back to html audio and reports autoplay rejection', async () => {
  let errorCount = 0
  let endedCount = 0
  let revokedUrl = null

  const player = createUnlockedAudioPlayer({
    AudioContextConstructor: null,
    createHtmlAudio: () => ({
      addEventListener() {},
      play: async () => {
        throw new Error('autoplay-blocked')
      },
      pause() {},
    }),
    createObjectURL: () => 'blob:fallback',
    revokeObjectURL: (url) => {
      revokedUrl = url
    },
  })

  await player.play({
    byteChunks: [new Uint8Array([9, 8, 7])],
    mimeType: 'audio/mpeg',
    onError: () => {
      errorCount += 1
    },
    onEnded: () => {
      endedCount += 1
    },
  })

  assert.equal(errorCount, 1)
  assert.equal(endedCount, 1)
  assert.equal(revokedUrl, 'blob:fallback')
})

test('createUnlockedAudioPlayer wraps streamed pcm chunks into a wav blob before playback', async () => {
  let capturedBlob = null

  class FakeBlob {
    constructor(parts, options = {}) {
      this.parts = parts
      this.type = options.type
      capturedBlob = this
    }
  }

  const player = createUnlockedAudioPlayer({
    BlobConstructor: FakeBlob,
    createHtmlAudio: () => ({
      src: '',
      muted: false,
      currentTime: 0,
      async play() {
        queueMicrotask(() => {
          this.onended?.()
        })
      },
      pause() {},
      load() {},
    }),
    createObjectURL: () => 'blob:pcm-segment',
    revokeObjectURL: () => {},
  })

  await player.play({
    byteChunks: [new Uint8Array([1, 0, 2, 0]), new Uint8Array([3, 0, 4, 0])],
    mimeType: 'audio/pcm',
    outputFormat: 'pcm',
  })

  await new Promise((resolve) => setTimeout(resolve, 0))

  assert.ok(capturedBlob)
  assert.equal(capturedBlob.type, 'audio/wav')
  const wavBytes = capturedBlob.parts[0]
  assert.equal(String.fromCharCode(...wavBytes.slice(0, 4)), 'RIFF')
  assert.equal(String.fromCharCode(...wavBytes.slice(8, 12)), 'WAVE')
  assert.equal(wavBytes.length, 52)
})

test('createTTSSegmentCollector keeps collecting late audio chunks after tts_end before finalizing', async () => {
  const completed = []
  const collector = createTTSSegmentCollector({
    graceMs: 5,
    onSegmentReady: (segment) => completed.push(segment),
  })

  collector.handle({
    type: 'tts_audio',
    segment_id: 'seg-1',
    payload: 'chunk-1',
    mime_type: 'audio/mpeg',
    output_format: 'mp3',
    sequence: 1,
  })
  collector.handle({
    type: 'tts_end',
    segment_id: 'seg-1',
    sequence: 1,
  })
  collector.handle({
    type: 'tts_audio',
    segment_id: 'seg-1',
    payload: 'chunk-2',
    mime_type: 'audio/mpeg',
    output_format: 'mp3',
    sequence: 1,
  })

  await new Promise((resolve) => setTimeout(resolve, 15))

  assert.deepEqual(completed, [
    {
      segmentId: 'seg-1',
      mimeType: 'audio/mpeg',
      outputFormat: 'mp3',
      sequence: 1,
      chunks: ['chunk-1', 'chunk-2'],
    },
  ])
})

test('createTTSSegmentCollector handles tts_end arriving before any audio chunks', async () => {
  const completed = []
  const collector = createTTSSegmentCollector({
    graceMs: 5,
    onSegmentReady: (segment) => completed.push(segment),
  })

  collector.handle({
    type: 'tts_end',
    segment_id: 'seg-2',
    sequence: 2,
  })
  collector.handle({
    type: 'tts_audio',
    segment_id: 'seg-2',
    payload: 'chunk-a',
    mime_type: 'audio/mpeg',
    output_format: 'mp3',
    sequence: 2,
  })
  collector.handle({
    type: 'tts_audio',
    segment_id: 'seg-2',
    payload: 'chunk-b',
    mime_type: 'audio/mpeg',
    output_format: 'mp3',
    sequence: 2,
  })

  await new Promise((resolve) => setTimeout(resolve, 15))

  assert.deepEqual(completed, [
    {
      segmentId: 'seg-2',
      mimeType: 'audio/mpeg',
      outputFormat: 'mp3',
      sequence: 2,
      chunks: ['chunk-a', 'chunk-b'],
    },
  ])
})
