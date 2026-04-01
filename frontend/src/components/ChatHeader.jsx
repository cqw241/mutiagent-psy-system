import { CameraIcon } from './Icons'

export default function ChatHeader({
    connectionState,
    onStartVideoCall,
    isVideoCallActive = false,
}) {
    return (
        <header className="mb-5 flex items-center justify-between rounded-[28px] border border-white/65 bg-white/70 px-5 py-4 shadow-[0_18px_60px_rgba(113,92,72,0.10)] backdrop-blur">
            <div>
                <p className="text-xs uppercase tracking-[0.32em] text-stone-400">Multi-Agent Support Console</p>
                <h1 className="mt-2 font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-2xl text-stone-800 md:text-3xl">
                    青年心理支持交互台
                </h1>
            </div>
            <div className="flex items-center gap-3">
                <button
                    type="button"
                    onClick={onStartVideoCall}
                    disabled={isVideoCallActive}
                    className="flex items-center gap-2 rounded-full border border-[#d9cdbd] bg-[#f8efe3] px-4 py-2 text-sm font-medium text-stone-700 transition hover:-translate-y-0.5 hover:bg-[#f4e7d7] disabled:cursor-default disabled:opacity-55"
                >
                    <CameraIcon className="h-4 w-4" />
                    {isVideoCallActive ? '视频通话中' : '进入视频通话'}
                </button>
                <div
                    className={`rounded-full px-4 py-2 text-sm ${connectionState === 'connected'
                            ? 'bg-emerald-50 text-emerald-700'
                            : connectionState === 'connecting'
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-red-50 text-red-700'
                        }`}
                >
                    {connectionState === 'connected' ? '文字连接稳定' : connectionState === 'connecting' ? '文字连接中' : '文字已断开'}
                </div>
            </div>
        </header>
    )
}
