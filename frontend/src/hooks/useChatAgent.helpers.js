export function finalizeAssistantMessages(messages, { currentStreamId, replyText, finalPayload, now = Date.now }) {
  let found = false

  const next = messages.map((item) => {
    if (currentStreamId && item.id === currentStreamId) {
      found = true
      return {
        ...item,
        text: replyText || item.text,
        streaming: false,
      }
    }
    return item
  })

  if (!found && replyText) {
    next.push({
      id: `assistant-final-${now()}`,
      role: 'assistant',
      text: replyText,
      streaming: false,
    })
  }

  if (finalPayload.referral_required && finalPayload.hotline_card) {
    next.push({
      id: `support-${now()}`,
      role: 'support',
      card: finalPayload.hotline_card,
    })
  }

  return next
}

export function appendVoiceTranscriptMessage(messages, transcriptText, { now = Date.now } = {}) {
  const text = typeof transcriptText === 'string' ? transcriptText.trim() : ''
  if (!text) {
    return messages
  }

  const lastMessage = messages[messages.length - 1]
  if (lastMessage?.role === 'user' && lastMessage?.text === text) {
    return messages
  }

  return [
    ...messages,
    {
      id: `voice-user-${now()}`,
      role: 'user',
      text,
    },
  ]
}
