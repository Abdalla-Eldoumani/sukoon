import { useRef, type KeyboardEvent } from 'react'

const STEP: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }

/**
 * Arrow keys move a radio group's choice, wrapping at the ends, and carry the focus to the
 * newly chosen radio. Spread the result onto the element that has role="radiogroup".
 */
export function useRadioArrows(count: number, current: number, choose: (index: number) => void) {
  const ref = useRef<HTMLDivElement>(null)
  const onKeyDown = (e: KeyboardEvent) => {
    const step = STEP[e.key]
    if (!step) return
    e.preventDefault()
    const next = (current + step + count) % count
    choose(next)
    ref.current?.querySelectorAll<HTMLButtonElement>('[role=radio]')[next]?.focus()
  }
  return { ref, onKeyDown }
}
