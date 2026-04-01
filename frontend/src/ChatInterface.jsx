import { useEffect, useRef, useState } from 'react'

import { useChatAgent } from './hooks/useChatAgent'
import { useFaceAnalysis } from './hooks/useFaceAnalysis'
import ChatHeader from './components/ChatHeader'
import StageIndicator from './components/StageIndicator'
import VoicePanel from './components/VoicePanel'
import FaceToggle from './components/FaceToggle'
import MessageList from './components/MessageList'
import InputCabin from './components/InputCabin'
import TracePanel from './components/TracePanel'
import VideoCallPanel from './components/VideoCallPanel'

export default function ChatInterface() {
  const [isTraceOpen, setIsTraceOpen] = useState(false)
  const [isVideoCallActive, setIsVideoCallActive] = useState(false)
  const [isVideoCameraEnabled, setIsVideoCameraEnabled] = useState(true)
  const pendingCallBootRef = useRef(false)

  const {
    sessionId,
    messages,
    input,
    setInput,
    connectionState,
    stageLabel,
    setStageLabel,
    latestTrace,
    handleSubmit,
    handleVoiceToggle,
    voiceStream,
    voiceSendFn,
    ttsPlayback,
  } = useChatAgent({
    responseAudio: isVideoCallActive,
    callMode: isVideoCallActive ? 'video' : 'standard',
  })

  const faceAnalysis = useFaceAnalysis({
    sendFn: voiceSendFn,
    enabled: isVideoCallActive && isVideoCameraEnabled,
  })

  useEffect(() => {
    if (!isVideoCallActive || !pendingCallBootRef.current) {
      return
    }

    pendingCallBootRef.current = false
    voiceStream.startStreaming()
    setStageLabel('视频通话已接通，你可以自然说话。')
  }, [isVideoCallActive, setStageLabel, voiceStream])

  const handleStartVideoCall = () => {
    if (faceAnalysis.isActive) {
      faceAnalysis.stop()
    }
    pendingCallBootRef.current = true
    setIsVideoCameraEnabled(true)
    setIsVideoCallActive(true)
  }

  const handleToggleVideoCamera = () => {
    setIsVideoCameraEnabled((current) => !current)
  }

  const handleEndVideoCall = () => {
    pendingCallBootRef.current = false
    setIsVideoCallActive(false)
    setIsVideoCameraEnabled(false)
    ttsPlayback.resetPlayback()
    voiceStream.stopStreaming()
    setStageLabel('视频通话已结束，已返回文字/按键语音模式。')
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#f5efe3_0%,#f7f1e8_42%,#edf1ec_100%)] text-stone-700">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-6 md:px-6 lg:px-8">
        <ChatHeader
          connectionState={connectionState}
          onStartVideoCall={handleStartVideoCall}
          isVideoCallActive={isVideoCallActive}
        />

        {isVideoCallActive ? (
          <main className="flex-1">
            <VideoCallPanel
              messages={messages}
              stageLabel={stageLabel}
              voiceStream={voiceStream}
              faceAnalysis={faceAnalysis}
              onToggleCamera={handleToggleVideoCamera}
              onEndCall={handleEndVideoCall}
              ttsPlayback={ttsPlayback}
            />
          </main>
        ) : (
          <main className="grid flex-1 gap-5 lg:grid-cols-[1.35fr_0.65fr]">
            <section className="flex min-h-[70vh] flex-col rounded-[34px] border border-white/70 bg-white/80 p-4 shadow-[0_20px_70px_rgba(118,99,79,0.11)] backdrop-blur md:p-5">
              <StageIndicator stageLabel={stageLabel} />

              <VoicePanel
                voiceStream={voiceStream}
                handleVoiceToggle={handleVoiceToggle}
              />

              <FaceToggle faceAnalysis={faceAnalysis} />

              <MessageList messages={messages} />

              <InputCabin
                input={input}
                setInput={setInput}
                handleSubmit={handleSubmit}
              />
            </section>

            <TracePanel
              sessionId={sessionId}
              latestTrace={latestTrace}
              isTraceOpen={isTraceOpen}
              setIsTraceOpen={setIsTraceOpen}
            />
          </main>
        )}
      </div>
    </div>
  )
}
