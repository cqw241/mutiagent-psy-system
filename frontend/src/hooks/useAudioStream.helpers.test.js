import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildVoiceControlPayload,
  shouldSendVoiceCommit,
} from './useAudioStream.helpers.js'

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

test('buildVoiceControlPayload primes the voice websocket with voice-input metadata', () => {
  assert.deepEqual(
    buildVoiceControlPayload({
      userProfile: { school: 'demo-university' },
      multimodalFeatures: {
        response_audio: true,
        call_mode: 'standard',
      },
      sampleRate: 16000,
    }),
    {
      user_profile: { school: 'demo-university' },
      multimodal_features: {
        response_audio: true,
        call_mode: 'standard',
        input_mode: 'voice',
        sample_rate: 16000,
      },
    },
  )
})

test('buildVoiceControlPayload attaches commit type when requested', () => {
  assert.deepEqual(
    buildVoiceControlPayload({
      type: 'input_audio_buffer.commit',
      multimodalFeatures: {
        response_audio: true,
        call_mode: 'video',
      },
      sampleRate: 16000,
    }),
    {
      type: 'input_audio_buffer.commit',
      user_profile: {},
      multimodal_features: {
        response_audio: true,
        call_mode: 'video',
        input_mode: 'voice',
        sample_rate: 16000,
      },
    },
  )
})
