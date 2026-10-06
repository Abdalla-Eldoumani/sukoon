import { useRef, type KeyboardEvent } from 'react'
import styles from './Segmented.module.css'

interface Props<T extends string> {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}

/** A radio group drawn as one control; the arrow keys move the choice. */
export function Segmented<T extends string>({ label, value, options, onChange }: Props<T>) {
  const group = useRef<HTMLDivElement>(null)
  const onKeyDown = (e: KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key]
    if (!step) return
    e.preventDefault()
    const at = options.findIndex((o) => o.value === value)
    const next = (at + step + options.length) % options.length
    onChange(options[next].value)
    group.current?.querySelectorAll<HTMLButtonElement>('[role=radio]')[next]?.focus()
  }
  return (
    <div ref={group} className={styles.group} role="radiogroup" aria-label={label} onKeyDown={onKeyDown}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          className={styles.segment}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
