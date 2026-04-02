export function finalizeAssistantMessages(messages, { currentStreamId, replyText, finalPayload, now = Date.now }) {
  let found = false

  const next = messages.map((item) => {
    if (currentStreamId && item.id === currentStreamId) {
      found = true
      return {
        ...item,
        text: replyText || item.text,
        streaming: false,
        typing: false,
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
      typing: true,
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

export function completeAssistantTyping(messages, messageId) {
  if (!messageId) {
    return messages
  }

  return messages.map((item) => {
    if (item.id !== messageId || item.role !== 'assistant' || !item.typing) {
      return item
    }

    return {
      ...item,
      typing: false,
    }
  })
}

export function appendAssistantStreamFrame(
  messages,
  frame,
  { currentStreamId, now = Date.now } = {},
) {
  const text = typeof frame === 'string' ? frame : ''
  if (!text) {
    return {
      messages,
      streamId: currentStreamId ?? null,
    }
  }

  if (!currentStreamId) {
    const nextStreamId = `assistant-${now()}`
    return {
      streamId: nextStreamId,
      messages: [
        ...messages,
        {
          id: nextStreamId,
          role: 'assistant',
          text,
          streaming: true,
        },
      ],
    }
  }

  let found = false
  const nextMessages = messages.map((item) => {
    if (item.id !== currentStreamId) {
      return item
    }

    found = true
    return {
      ...item,
      text: `${item.text}${text}`,
      streaming: true,
    }
  })

  if (found) {
    return {
      messages: nextMessages,
      streamId: currentStreamId,
    }
  }

  return {
    streamId: currentStreamId,
    messages: [
      ...messages,
      {
        id: currentStreamId,
        role: 'assistant',
        text,
        streaming: true,
      },
    ],
  }
}

export function applyAssistantTokenFrame({
  messages,
  tokenBuffer = '',
  frame,
  currentStreamId,
  now = Date.now,
} = {}) {
  const text = typeof frame === 'string' ? frame : ''
  if (!text) {
    return {
      messages,
      tokenBuffer,
      streamId: currentStreamId ?? null,
    }
  }

  const streamResult = appendAssistantStreamFrame(messages, text, {
    currentStreamId,
    now,
  })

  return {
    messages: streamResult.messages,
    tokenBuffer: `${tokenBuffer}${text}`,
    streamId: streamResult.streamId,
  }
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

export function buildTurnMultimodalFeatures({
  inputMode = 'text',
  responseAudio = false,
  callMode = 'standard',
} = {}) {
  return {
    response_audio: inputMode === 'voice' ? true : Boolean(responseAudio),
    call_mode: callMode,
  }
}
