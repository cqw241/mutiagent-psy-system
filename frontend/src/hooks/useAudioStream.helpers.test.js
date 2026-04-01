import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldSendVoiceCommit } from './useAudioStream.helpers.js'

test('shouldSendVoiceCommit suppresses redundant commit in standard mode after transcript arrived', () => {
  assert.equal(
    shouldSendVoiceCommit({
      callMode: 'standard',
      hasTranscriptSinceRecordingStart: true,
    }),
    false,
  )
})

test('shouldSendVoiceCommit still commits in standard mode when no transcript arrived yet', () => {
  assert.equal(
    shouldSendVoiceCommit({
      callMode: 'standard',
      hasTranscriptSinceRecordingStart: false,
    }),
    true,
  )
})

test('shouldSendVoiceCommit keeps commit enabled in video mode for tail flush', () => {
  assert.equal(
    shouldSendVoiceCommit({
      callMode: 'video',
      hasTranscriptSinceRecordingStart: true,
    }),
    true,
  )
})
