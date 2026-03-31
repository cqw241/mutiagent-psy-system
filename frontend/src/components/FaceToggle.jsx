import { CameraIcon } from './Icons'
import { motion } from 'framer-motion'

export default function FaceToggle({ faceAnalysis }) {
    const statusLabel = faceAnalysis.isActive
        ? faceAnalysis.isCameraReady
            ? '摄像头已开启'
            : '正在初始化...'
        : '摄像头未启动'

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 rounded-[30px] border border-[#d6ccc0] bg-[linear-gradient(145deg,#f8f2ea_0%,#eee8df_100%)] p-5 shadow-[0_12px_35px_rgba(130,111,88,0.06)]"
        >
            <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                    <p className="text-xs uppercase tracking-[0.32em] text-stone-400">Face Channel</p>
                    <p className="mt-1.5 font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-xl text-stone-800">
                        表情感知
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-stone-500">
                        仅本地分析，不上传任何画面。
                    </p>
                </div>

                <div className="flex items-center gap-3">
                    <div className="rounded-full bg-white/80 px-3.5 py-1.5 text-sm font-medium text-stone-600">
                        {statusLabel}
                    </div>
                    <button
                        type="button"
                        onClick={faceAnalysis.toggle}
                        className={`relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-white shadow-[0_12px_28px_rgba(125,99,77,0.16)] transition-all duration-300 hover:scale-105 active:scale-95 ${
                            faceAnalysis.isActive
                                ? 'bg-[#a2675f] hover:bg-[#91544d]'
                                : 'bg-[#8ca49b] hover:bg-[#7a968c]'
                        }`}
                        aria-label={faceAnalysis.isActive ? '关闭摄像头' : '开启摄像头'}
                    >
                        {faceAnalysis.isActive && (
                            <span className="absolute inset-0 -z-10 animate-pulse rounded-full bg-[#a2675f] opacity-30" />
                        )}
                        <CameraIcon />
                    </button>
                </div>
            </div>

            {faceAnalysis.cameraError && (
                <p className="mt-3 rounded-2xl border border-rose-100 bg-rose-50 px-4 py-2.5 text-xs leading-5 text-rose-700">
                    {faceAnalysis.cameraError}
                </p>
            )}

            {/* Hidden video element for MediaPipe — never displayed */}
            <video
                ref={faceAnalysis.videoRef}
                className="hidden"
                playsInline
                muted
                width={320}
                height={240}
            />
        </motion.div>
    )
}
