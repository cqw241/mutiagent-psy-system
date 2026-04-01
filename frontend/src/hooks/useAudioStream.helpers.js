export function shouldSendVoiceCommit({
  callMode = 'standard',
  hasTranscriptSinceRecordingStart = false,
} = {}) {
  if (callMode === 'standard' && hasTranscriptSinceRecordingStart) {
    return false
  }

  return true
}

export function buildVoiceControlPayload({
  type,
  userProfile = {},
  multimodalFeatures = {},
  sampleRate,
} = {}) {
  const payload = {
    user_profile: userProfile,
    multimodal_features: {
      ...multimodalFeatures,
      input_mode: 'voice',
      sample_rate: sampleRate,
    },
  }

  if (type) {
    payload.type = type
  }

  return payload
}
