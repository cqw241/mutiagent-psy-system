import TypewriterText from './TypewriterText'
import { motion } from 'framer-motion'

export default function MessageList({ messages, finalizePendingAssistantReply }) {
    return (
        <div className="flex-1 space-y-4 overflow-y-auto px-1 py-4">
            {messages.map((message) => {
                if (message.role === 'support') {
                    return (
                        <motion.div
                            initial={{ opacity: 0, y: 10, scale: 0.95 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            transition={{ duration: 0.4, ease: 'easeOut' }}
                            key={message.id}
                            className="rounded-[28px] border border-[#d8cbb8] bg-[linear-gradient(135deg,#f7efe4_0%,#eef3ea_100%)] p-5 text-left shadow-[0_16px_45px_rgba(130,111,88,0.10)]"
                        >
                            <p className="font-['Iowan_Old_Style','Palatino_Linotype','Songti_SC',serif] text-xl text-stone-800">
                                {message.card.title}
                            </p>
                            <p className="mt-3 text-base font-medium text-stone-700">{message.card.hotline}</p>
                            <ul className="mt-3 space-y-2 text-sm leading-6 text-stone-600">
                                {message.card.tips.map((tip) => (
                                    <li key={tip} className="rounded-2xl bg-white/75 px-3 py-2">
                                        {tip}
                                    </li>
                                ))}
                            </ul>
                        </motion.div>
                    )
                }

                const isUser = message.role === 'user'
                return (
                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3, ease: 'easeOut' }}
                        key={message.id}
                        className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`max-w-[82%] rounded-[28px] px-5 py-4 text-left shadow-[0_12px_30px_rgba(130,111,88,0.08)] ${isUser
                                    ? 'rounded-br-sm bg-[#dfe7df] text-stone-700'
                                    : 'rounded-bl-sm bg-[#fbf7f1] text-stone-700'
                                }`}
                        >
                            <p className="whitespace-pre-wrap text-[15px] leading-7">
                                {message.streaming ? (
                                    <TypewriterText
                                        text={message.text}
                                        active={message.streaming}
                                        onDone={finalizePendingAssistantReply}
                                    />
                                ) : (
                                    message.text
                                )}
                                {message.streaming ? (
                                    <span className="ml-1 inline-block h-5 w-2 animate-pulse rounded-full bg-stone-400/70 align-middle" />
                                ) : null}
                            </p>
                        </div>
                    </motion.div>
                )
            })}
        </div>
    )
}
