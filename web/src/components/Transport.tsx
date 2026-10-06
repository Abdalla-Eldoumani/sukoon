import { useRef, type PointerEvent } from 'react'
import { clock } from '../format'
import { PauseIcon, PlayIcon } from './icons'
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
  const pointer = useRef(false)
  const press = (e: PointerEvent<HTMLButtonElement>) => {
    // Captured, so letting go anywhere still ends a hold.
    e.currentTarget.setPointerCapture?.(e.pointerId)
    pointer.current = true
    holding.current = false
    timer.current = setTimeout(() => {
      holding.current = true
      onHold(true)
    }, HOLD_MS)
  }
  const release = (toggle: boolean) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    if (holding.current) onHold(false)
    else if (toggle) onToggle()
    holding.current = false
  }
  const click = () => {
    // A pointer press was handled on release; keyboards and screen readers arrive here.
    if (pointer.current) {
      pointer.current = false
      return
    }
    onToggle()
  }
  return (
    <div className={styles.transport}>
      <button
        type="button"
        className="btn-quiet btn-icon"
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
        <span className="label" aria-hidden="true">
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
          onPointerCancel={() => release(false)}
          onLostPointerCapture={() => release(false)}
          onClick={click}
        >
          <span className={styles.knob} />
        </button>
        <span className="label" aria-hidden="true">
          Original
        </span>
      </div>
    </div>
  )
}
