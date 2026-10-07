import { useEffect, useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { clock } from '../../lib/text/format'
import { PauseIcon, PlayIcon } from '../ui/icons'
import styles from './Transport.module.css'

const HOLD_MS = 300

interface Props {
  playing: boolean
  current: number
  duration: number
  original: boolean
  onPlay: () => void
  onPause: () => void
  /** A click flips the switch for good. */
  onToggle: () => void
  /** Pressing and holding plays the original only while held. */
  onHold: (held: boolean) => void
}

export function Transport({ playing, current, duration, original, onPlay, onPause, onToggle, onHold }: Props) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const holding = useRef(false)
  // A primary press is down; and, separately, its click is still to come.
  const pressed = useRef(false)
  const pointer = useRef(false)
  // Closing the panel mid-press must not start a hold afterwards.
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )
  const press = (e: PointerEvent<HTMLButtonElement>) => {
    // Only the primary button: a right click opens the menu and sends no click to match.
    if (e.button > 0) return
    // Captured, so letting go anywhere still ends a hold.
    e.currentTarget.setPointerCapture?.(e.pointerId)
    pressed.current = true
    pointer.current = true
    holding.current = false
    timer.current = setTimeout(() => {
      holding.current = true
      onHold(true)
    }, HOLD_MS)
  }
  const release = (toggle: boolean) => {
    if (!pressed.current) return
    pressed.current = false
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    if (holding.current) onHold(false)
    else if (toggle) onToggle()
    holding.current = false
  }
  const cancel = () => {
    release(false)
    // The browser took the pointer back, so no click follows.
    pointer.current = false
  }
  const click = () => {
    // A pointer press was handled on release; keyboards and screen readers arrive here.
    if (pointer.current) {
      pointer.current = false
      return
    }
    onToggle()
  }
  const key = (e: KeyboardEvent<HTMLButtonElement>) => {
    // A key press is never the tail of a pointer press.
    pointer.current = false
    // Holding Enter would flip the switch on every repeat.
    if (e.key === 'Enter' && e.repeat) e.preventDefault()
  }
  return (
    <div className={styles.transport}>
      <button
        type="button"
        className={`btn-quiet btn-icon ${styles.play}`}
        aria-label={playing ? 'Pause' : 'Play'}
        title={playing ? 'Pause' : 'Play'}
        onClick={playing ? onPause : onPlay}
      >
        {playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <span className="readout-lg">
        {clock(current)} <span className={styles.total}>/ {clock(duration)}</span>
      </span>
      <div className={styles.compare}>
        <span className="small" aria-hidden="true">
          Clean
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={original}
          aria-label="Play the original (hold C)"
          className={styles.switch}
          onPointerDown={press}
          onPointerUp={() => release(true)}
          onPointerCancel={cancel}
          onLostPointerCapture={() => release(false)}
          onClick={click}
          onKeyDown={key}
        >
          <span className={styles.knob} />
        </button>
        <span className="small" aria-hidden="true">
          Original
        </span>
        <span className={`small ${styles.hint}`} aria-hidden="true">
          hold C to compare
        </span>
      </div>
    </div>
  )
}
