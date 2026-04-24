import { SendIcon } from './Icons'
import { motion as Motion } from 'framer-motion'

export default function InputCabin({ input, setInput, handleSubmit }) {
    return (
        <Motion.form
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            onSubmit={handleSubmit}
            className="mt-4 rounded-[32px] border border-[#e8dccb] bg-white/60 p-3 shadow-[0_12px_35px_rgba(145,120,95,0.08)] backdrop-blur-md transition-all focus-within:bg-white/80 focus-within:shadow-[0_12px_45px_rgba(145,120,95,0.12)]"
        >
            <div className="flex items-end gap-3">
                <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSubmit(e);
                        }
                    }}
                    placeholder="你也可以继续用文字输入，把此刻最想说的一句话放在这里。"
                    className="min-h-[88px] flex-1 resize-none rounded-[28px] border border-transparent bg-[#f8f1e7]/80 px-5 py-4 text-[15px] leading-7 text-stone-700 outline-none transition placeholder:text-stone-400 focus:border-[#c9baa2] focus:bg-white"
                />
                <button
                    type="submit"
                    disabled={!input.trim()}
                    className="flex h-14 w-14 items-center justify-center rounded-full bg-[#8ca49b] text-white transition hover:bg-[#7a968c] hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 disabled:hover:bg-[#8ca49b]"
                    aria-label="发送消息"
                >
                    <SendIcon />
                </button>
            </div>
        </Motion.form>
    )
}
