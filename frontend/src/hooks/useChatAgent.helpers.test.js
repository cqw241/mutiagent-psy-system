import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appendVoiceTranscriptMessage,
  finalizeAssistantMessages,
} from './useChatAgent.helpers.js'

test('finalizeAssistantMessages merges the final reply into the active streaming bubble', () => {
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
  })
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
