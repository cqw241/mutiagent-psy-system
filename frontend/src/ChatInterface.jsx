import { useState } from 'react'

import { useChatAgent } from './hooks/useChatAgent'
import ChatHeader from './components/ChatHeader'
import StageIndicator from './components/StageIndicator'
import VoicePanel from './components/VoicePanel'
import MessageList from './components/MessageList'
import InputCabin from './components/InputCabin'
import TracePanel from './components/TracePanel'

export default function ChatInterface() {
  const {
    sessionId,
    messages,
    input,
    setInput,
    connectionState,
    stageLabel,
    latestTrace,
    handleSubmit,
    handleVoiceToggle,
    voiceStream,
    finalizePendingAssistantReply,
  } = useChatAgent()

  const [isTraceOpen, setIsTraceOpen] = useState(false)

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#f5efe3_0%,#f7f1e8_42%,#edf1ec_100%)] text-stone-700">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-6 md:px-6 lg:px-8">
        <ChatHeader connectionState={connectionState} />

        <main className="grid flex-1 gap-5 lg:grid-cols-[1.35fr_0.65fr]">
          <section className="flex min-h-[70vh] flex-col rounded-[34px] border border-white/70 bg-white/80 p-4 shadow-[0_20px_70px_rgba(118,99,79,0.11)] backdrop-blur md:p-5">
            <StageIndicator stageLabel={stageLabel} />

            <VoicePanel
              voiceStream={voiceStream}
              handleVoiceToggle={handleVoiceToggle}
            />

            <MessageList
              messages={messages}
              finalizePendingAssistantReply={finalizePendingAssistantReply}
            />

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
      </div>
    </div>
  )
}

