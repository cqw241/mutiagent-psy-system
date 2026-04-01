export function shouldSendVoiceCommit({
  callMode = 'standard',
  hasTranscriptSinceRecordingStart = false,
} = {}) {
  if (callMode === 'standard' && hasTranscriptSinceRecordingStart) {
    return false
  }

  return true
}
