import { useRef } from 'react'
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
  const press = () => {
    holding.current = false
    timer.current = setTimeout(() => {
      holding.current = true
      onHold(true)
    }, HOLD_MS)
  }
  const release = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    if (holding.current) onHold(false)
    else onToggle()
    holding.current = false
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
          onPointerUp={release}
          onPointerCancel={release}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              if (!e.repeat) onToggle()
            }
          }}
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
