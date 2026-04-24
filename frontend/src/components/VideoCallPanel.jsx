import { motion as Motion } from 'framer-motion'

import { CameraIcon, CameraOffIcon, PhoneOffIcon, WaveIcon } from './Icons'
import TypewriterText from './TypewriterText'
import { shouldMountLocalCameraVideo } from './VideoCallPanel.helpers'

function CallControlButton({
  label,
  onClick,
  icon,
  tone = 'soft',
}) {
  const toneClass =
    tone === 'danger'
      ? 'bg-[#a95854] text-white shadow-[0_18px_38px_rgba(169,88,84,0.28)] hover:bg-[#974743]'
      : 'bg-white/92 text-stone-700 shadow-[0_18px_34px_rgba(128,105,82,0.18)] hover:bg-white'

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group flex h-20 w-20 flex-col items-center justify-center rounded-full transition duration-300 hover:-translate-y-0.5 ${toneClass}`}
      aria-label={label}
    >
      <span className="flex h-8 w-8 items-center justify-center">{icon}</span>
      <span className="mt-1 text-[11px] font-medium tracking-[0.16em] uppercase">
        {label}
      </span>
    </button>
  )
}

function TranscriptBubble({ message, onAssistantTypingDone }) {
  if (message.role === 'support') {
    return (
      <div className="rounded-[26px] border border-[#dbcdbd] bg-white/78 p-5 shadow-[0_18px_42px_rgba(128,105,82,0.12)] backdrop-blur">
        <p className="font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-xl text-stone-800">
          {message.card.title}
        </p>
        <p className="mt-2 text-sm font-medium text-stone-700">{message.card.hotline}</p>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-stone-600">
          {message.card.tips.map((tip) => (
            <li key={tip} className="rounded-2xl bg-[#f8f2ea] px-3 py-2">
              {tip}
            </li>
          ))}
        </ul>
      </div>
    )
  }

  const isUser = message.role === 'user'
  const isTypingAssistantReply = message.role === 'assistant' && message.typing

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[86%] rounded-[28px] px-5 py-4 shadow-[0_16px_34px_rgba(128,105,82,0.10)] ${
          isUser
            ? 'rounded-br-sm bg-[#dfe8de] text-stone-700'
            : 'rounded-bl-sm border border-white/55 bg-white/84 text-stone-700'
        }`}
      >
        <p className="whitespace-pre-wrap text-[15px] leading-7">
          {isTypingAssistantReply ? (
            <TypewriterText
              text={message.text}
              active
              onDone={() => onAssistantTypingDone?.(message.id)}
            />
          ) : (
            message.text
          )}
          {message.streaming || isTypingAssistantReply ? (
            <span className="ml-1 inline-block h-5 w-2 animate-pulse rounded-full bg-stone-400/70 align-middle" />
          ) : null}
        </p>
      </div>
    </div>
  )
}

export default function VideoCallPanel({
  messages,
  onAssistantTypingDone,
  stageLabel,
  voiceStream,
  faceCameraError,
  faceVideoRef,
  isFaceActive,
  isFaceCameraReady,
  onToggleCamera,
  onEndCall,
  ttsPlayback,
}) {
  const transcriptMessages = messages.slice(-8)
  const shouldShowCameraPreview = isFaceActive && isFaceCameraReady
  const shouldMountCameraVideo = shouldMountLocalCameraVideo({
    isActive: isFaceActive,
    isCameraReady: isFaceCameraReady,
  })

  return (
    <section className="relative min-h-[78vh] overflow-hidden rounded-[38px] border border-white/70 bg-[linear-gradient(135deg,rgba(255,250,244,0.98)_0%,rgba(246,239,229,0.96)_52%,rgba(235,243,235,0.96)_100%)] shadow-[0_30px_90px_rgba(118,99,79,0.14)]">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -left-10 top-8 h-52 w-52 rounded-full bg-[#f1dcc5]/45 blur-3xl" />
          <div className="absolute bottom-10 right-20 h-60 w-60 rounded-full bg-[#d6e3d8]/55 blur-3xl" />
        <div className="absolute inset-x-12 top-20 h-px bg-[linear-gradient(90deg,transparent,rgba(169,145,117,0.38),transparent)]" />
      </div>

      <div className="relative flex min-h-[78vh] flex-col px-6 py-6 md:px-8 md:py-7">
        <div className="flex flex-wrap items-start justify-between gap-4 pr-0 md:pr-[250px]">
          <div>
            <p className="text-xs uppercase tracking-[0.34em] text-stone-400">Video Call Mode</p>
            <h2 className="mt-2 font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-[30px] leading-tight text-stone-800">
              陪伴式语音通话
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-500">
              语音、表情与文本会同时协作；画面仅在浏览器本地用于分析，不会上传原始视频。
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-white/78 px-4 py-2 text-xs font-medium tracking-[0.18em] text-stone-500 shadow-[0_12px_24px_rgba(128,105,82,0.10)]">
              {stageLabel}
            </span>
            <span className="rounded-full bg-[#edf4ee] px-4 py-2 text-xs font-medium tracking-[0.18em] text-[#6b867c]">
              {voiceStream.isRecording ? '正在听你说' : '麦克风待命'}
            </span>
            <span className="rounded-full bg-[#f6eee4] px-4 py-2 text-xs font-medium tracking-[0.18em] text-[#9b7e60]">
              {ttsPlayback.isPlaying ? '语音回复播放中' : '语音回复待命'}
            </span>
          </div>
        </div>

        <Motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-8 flex-1 overflow-hidden rounded-[32px] border border-white/65 bg-white/48 p-4 shadow-inner backdrop-blur md:p-6"
        >
          <div className="flex h-full flex-col gap-5 overflow-y-auto pr-0 md:pr-[250px]">
            {voiceStream.liveTranscript ? (
              <div className="rounded-[26px] border border-[#d9dcca] bg-[#edf4ee]/82 px-5 py-4 text-sm leading-6 text-stone-700">
                <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.26em] text-[#6b867c]">
                  <WaveIcon className="h-4 w-4" />
                  正在捕捉你的表达
                </div>
                <p>{voiceStream.liveTranscript}</p>
              </div>
            ) : null}

            {transcriptMessages.map((message) => (
              <TranscriptBubble
                key={message.id}
                message={message}
                onAssistantTypingDone={onAssistantTypingDone}
              />
            ))}
          </div>
        </Motion.div>

        <div className="pointer-events-none absolute right-6 top-6 w-[210px] md:right-8 md:top-8 md:w-[228px]">
          <div className="pointer-events-auto overflow-hidden rounded-[30px] border border-white/70 bg-[#f7efe5]/82 p-3 shadow-[0_24px_54px_rgba(118,99,79,0.18)] backdrop-blur">
            <div className="mb-3 flex items-center justify-between px-1">
              <div>
                <p className="text-[11px] uppercase tracking-[0.28em] text-stone-400">Local Camera</p>
                <p className="mt-1 text-sm font-medium text-stone-700">
                  {isFaceActive && isFaceCameraReady ? '本地摄像头在线' : '摄像头已关闭'}
                </p>
              </div>
              <span className="rounded-full bg-white/80 px-2.5 py-1 text-[11px] text-stone-500">
                Edge
              </span>
            </div>

            <div className="relative aspect-[3/4] w-full overflow-hidden rounded-[24px]">
              {shouldMountCameraVideo ? (
                <video
                  ref={faceVideoRef}
                  className={`h-full w-full object-cover shadow-[0_18px_28px_rgba(118,99,79,0.14)] transition-opacity duration-300 ${
                    shouldShowCameraPreview ? 'opacity-100' : 'opacity-0'
                  }`}
                  playsInline
                  muted
                  autoPlay
                />
              ) : null}
              {!shouldShowCameraPreview ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center border border-dashed border-[#d5c7b5] bg-[linear-gradient(180deg,#fff8ef_0%,#f0e6d9_100%)] px-5 text-center text-sm leading-6 text-stone-500">
                  <CameraOffIcon className="mb-3 h-8 w-8 text-stone-400" />
                  摄像头关闭时，系统只保留语音与文本链路。
                </div>
              ) : null}
            </div>

            {faceCameraError ? (
              <p className="mt-3 rounded-2xl border border-rose-100 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">
                {faceCameraError}
              </p>
            ) : null}
            {ttsPlayback.playbackError ? (
              <p className="mt-3 rounded-2xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">
                {ttsPlayback.playbackError}
              </p>
            ) : null}
          </div>
        </div>

        <div className="mt-8 flex justify-center">
          <div className="flex items-center gap-5 rounded-full border border-white/70 bg-white/58 px-5 py-4 shadow-[0_18px_40px_rgba(118,99,79,0.14)] backdrop-blur">
            <CallControlButton
              label={isFaceActive ? '关闭镜头' : '打开镜头'}
              onClick={onToggleCamera}
              icon={
                isFaceActive
                  ? <CameraOffIcon className="h-6 w-6" />
                  : <CameraIcon className="h-6 w-6" />
              }
            />
            <CallControlButton
              label="结束通话"
              onClick={onEndCall}
              icon={<PhoneOffIcon className="h-6 w-6" />}
              tone="danger"
            />
          </div>
        </div>
      </div>
    </section>
  )
}
