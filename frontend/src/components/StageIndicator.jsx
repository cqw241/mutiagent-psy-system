import { motion as Motion, AnimatePresence } from 'framer-motion'

export default function StageIndicator({ stageLabel }) {
    return (
        <div className="mb-4 overflow-hidden rounded-[24px] border border-[#e8dccb] bg-[#fdfbf7] shadow-sm">
            <AnimatePresence mode="wait">
                <Motion.div
                    key={stageLabel}
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    transition={{ duration: 0.3 }}
                    className="flex items-center px-5 py-3 text-sm text-stone-600"
                >
                    <span className="mr-3 inline-block h-2.5 w-2.5 shrink-0 animate-pulse rounded-full bg-[#8ea691]" />
                    <span className="text-stone-600/90">{stageLabel}</span>
                </Motion.div>
            </AnimatePresence>
        </div>
    )
}
