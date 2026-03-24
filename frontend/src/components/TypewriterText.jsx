import { useEffect, useMemo, useRef, useState } from 'react'
import { DEFAULT_TYPEWRITER_INTERVAL_MS } from '../lib/typewriterStream'

export default function TypewriterText({ text, active, onDone }) {
    const characters = useMemo(() => Array.from(text ?? ''), [text])
    const [visibleCount, setVisibleCount] = useState(active ? 0 : characters.length)
    const doneRef = useRef(false)
    const onDoneRef = useRef(onDone)

    useEffect(() => {
        onDoneRef.current = onDone
    }, [onDone])

    useEffect(() => {
        doneRef.current = false
        setVisibleCount(active ? 0 : characters.length)
    }, [active, characters.length, text])

    useEffect(() => {
        if (!active) {
            return
        }

        if (visibleCount >= characters.length) {
            if (!doneRef.current) {
                doneRef.current = true
                onDoneRef.current?.()
            }
            return
        }

        const timerId = window.setTimeout(() => {
            setVisibleCount((current) => Math.min(current + 1, characters.length))
        }, DEFAULT_TYPEWRITER_INTERVAL_MS)

        return () => {
            window.clearTimeout(timerId)
        }
    }, [active, characters.length, visibleCount])

    return characters.slice(0, active ? visibleCount : characters.length).join('')
}
