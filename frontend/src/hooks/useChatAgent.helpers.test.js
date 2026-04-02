import assert from 'node:assert/strict'
import test from 'node:test'

import {
  applyAssistantTokenFrame,
  appendAssistantStreamFrame,
  appendVoiceTranscriptMessage,
  buildTurnMultimodalFeatures,
  completeAssistantTyping,
  finalizeAssistantMessages,
} from './useChatAgent.helpers.js'

test('finalizeAssistantMessages merges the final reply into the active streaming bubble without restarting typing', () => {
  const messages = [
    { id: 'welcome', role: 'assistant', text: '你好' },
    { id: 'assistant-1', role: 'assistant', text: '抱抱你，', streaming: true },
  ]

  const next = finalizeAssistantMessages(messages, {
    currentStreamId: 'assistant-1',
    replyText: '抱抱你，听到你心情不好，我也很担心。',
    finalPayload: {
      referral_required: false,
      hotline_card: null,
    },
  })

  assert.equal(next.length, 2)
  assert.deepEqual(next[1], {
    id: 'assistant-1',
    role: 'assistant',
    text: '抱抱你，听到你心情不好，我也很担心。',
    streaming: false,
    typing: false,
  })
})

test('finalizeAssistantMessages marks a new final assistant reply for render-layer typing', () => {
  const messages = [{ id: 'welcome', role: 'assistant', text: '你好' }]

  const next = finalizeAssistantMessages(messages, {
    currentStreamId: null,
    replyText: '我在这里，先陪你把这段感受慢慢说完。',
    finalPayload: {
      referral_required: false,
      hotline_card: null,
    },
    now: () => 42,
  })

  assert.deepEqual(next[1], {
    id: 'assistant-final-42',
    role: 'assistant',
    text: '我在这里，先陪你把这段感受慢慢说完。',
    streaming: false,
    typing: true,
  })
})

test('completeAssistantTyping only clears the typing flag for the targeted assistant reply', () => {
  const messages = [
    { id: 'welcome', role: 'assistant', text: '你好' },
    { id: 'assistant-final-42', role: 'assistant', text: '我在这里。', streaming: false, typing: true },
    { id: 'assistant-final-43', role: 'assistant', text: '另一条消息', streaming: false, typing: true },
  ]

  const next = completeAssistantTyping(messages, 'assistant-final-42')

  assert.deepEqual(next, [
    { id: 'welcome', role: 'assistant', text: '你好' },
    { id: 'assistant-final-42', role: 'assistant', text: '我在这里。', streaming: false, typing: false },
    { id: 'assistant-final-43', role: 'assistant', text: '另一条消息', streaming: false, typing: true },
  ])
})

test('appendVoiceTranscriptMessage ignores blank transcript payloads', () => {
  const messages = [{ id: 'welcome', role: 'assistant', text: '你好' }]

  const next = appendVoiceTranscriptMessage(messages, '   ')

  assert.deepEqual(next, messages)
})

test('appendVoiceTranscriptMessage avoids duplicating the same trailing user transcript', () => {
  const messages = [
    { id: 'welcome', role: 'assistant', text: '你好' },
    { id: 'voice-user-1', role: 'user', text: '我觉得心情很差' },
  ]

  const next = appendVoiceTranscriptMessage(messages, '我觉得心情很差')

  assert.deepEqual(next, messages)
})

test('appendAssistantStreamFrame creates a streaming assistant bubble on the first frame', () => {
  const result = appendAssistantStreamFrame(
    [{ id: 'welcome', role: 'assistant', text: '你好' }],
    '抱',
  )

  assert.equal(result.streamId.startsWith('assistant-'), true)
  assert.deepEqual(result.messages[1], {
    id: result.streamId,
    role: 'assistant',
    text: '抱',
    streaming: true,
  })
})

test('appendAssistantStreamFrame appends subsequent frames to the active assistant bubble', () => {
  const result = appendAssistantStreamFrame(
    [
      { id: 'welcome', role: 'assistant', text: '你好' },
      { id: 'assistant-1', role: 'assistant', text: '抱', streaming: true },
    ],
    '抱',
    { currentStreamId: 'assistant-1' },
  )

  assert.equal(result.streamId, 'assistant-1')
  assert.deepEqual(result.messages[1], {
    id: 'assistant-1',
    role: 'assistant',
    text: '抱抱',
    streaming: true,
  })
})

test('applyAssistantTokenFrame immediately projects token text into a streaming assistant bubble', () => {
  const result = applyAssistantTokenFrame({
    messages: [{ id: 'welcome', role: 'assistant', text: '你好' }],
    tokenBuffer: '',
    frame: '先',
    currentStreamId: null,
    now: () => 42,
  })

  assert.equal(result.streamId, 'assistant-42')
  assert.equal(result.tokenBuffer, '先')
  assert.deepEqual(result.messages[1], {
    id: 'assistant-42',
    role: 'assistant',
    text: '先',
    streaming: true,
  })
})

test('applyAssistantTokenFrame appends text and token buffer for the active stream bubble', () => {
  const result = applyAssistantTokenFrame({
    messages: [
      { id: 'welcome', role: 'assistant', text: '你好' },
      { id: 'assistant-1', role: 'assistant', text: '先', streaming: true },
    ],
    tokenBuffer: '先',
    frame: '深呼吸。',
    currentStreamId: 'assistant-1',
  })

  assert.equal(result.streamId, 'assistant-1')
  assert.equal(result.tokenBuffer, '先深呼吸。')
  assert.deepEqual(result.messages[1], {
    id: 'assistant-1',
    role: 'assistant',
    text: '先深呼吸。',
    streaming: true,
  })
})

test('buildTurnMultimodalFeatures forces response audio for voice-triggered turns', () => {
  assert.deepEqual(
    buildTurnMultimodalFeatures({
      inputMode: 'voice',
      responseAudio: false,
      callMode: 'standard',
    }),
    {
      response_audio: true,
      call_mode: 'standard',
    },
  )
})

test('buildTurnMultimodalFeatures keeps text-triggered turns text-only by default', () => {
  assert.deepEqual(
    buildTurnMultimodalFeatures({
      inputMode: 'text',
      responseAudio: false,
      callMode: 'standard',
    }),
    {
      response_audio: false,
      call_mode: 'standard',
    },
  )
})
