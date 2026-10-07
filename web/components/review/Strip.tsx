import { useCallback, useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { clock } from '../../lib/text/format'
import { cssVar, paintLanes, useCanvas, type Peaks } from '../../lib/review/lanes'
import styles from './Strip.module.css'

export type { Peaks } from '../../lib/review/lanes'

const RULER = 20
const LANE = 100
const STEP_S = 5
const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200]

interface Props {
  peaks: Peaks
  current: number
  onSeek: (seconds: number) => void
}

export function Strip({ peaks, current, onSeek }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const area = useRef<HTMLDivElement>(null)

  const paint = useCallback(
    (ctx: CanvasRenderingContext2D, width: number) => {
      const el = canvas.current!
      ctx.fillStyle = cssVar(el, '--rule')
      ctx.fillRect(0, RULER - 1, width, 1)
      ctx.fillRect(0, RULER + LANE, width, 1)
      // Ticks at a round step, at most one label per 80px so they never run into each other.
      const most = Math.max(1, Math.floor(width / 80))
      const step = STEPS.find((s) => peaks.seconds / s <= most) ?? peaks.seconds
      ctx.fillStyle = cssVar(el, '--text-2')
      ctx.font = `450 12px ${cssVar(el, '--font-mono')}`
      ctx.textBaseline = 'top'
      for (let t = 0; t < peaks.seconds; t += step) {
        const x = Math.round((t / peaks.seconds) * width)
        ctx.fillRect(x, RULER - 7, 1, 6)
        const label = clock(t)
        if (x + 6 + ctx.measureText(label).width <= width) ctx.fillText(label, x + 6, 0)
      }
      paintLanes(ctx, el, peaks, width, { top: RULER, lane: LANE, gap: 1, bar: 2, step: 3 })
    },
    [peaks],
  )
  useCanvas(canvas, paint)

  const seekTo = (clientX: number) => {
    const box = area.current?.getBoundingClientRect()
    if (!box || box.width === 0) return
    const fraction = Math.min(1, Math.max(0, (clientX - box.left) / box.width))
    onSeek(fraction * peaks.seconds)
  }
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture?.(e.pointerId)
    seekTo(e.clientX)
  }
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) seekTo(e.clientX)
  }
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = { ArrowLeft: -STEP_S, ArrowRight: STEP_S }
    if (e.key in moves) onSeek(Math.min(peaks.seconds, Math.max(0, current + moves[e.key])))
    else if (e.key === 'Home') onSeek(0)
    else if (e.key === 'End') onSeek(peaks.seconds)
    else return
    e.preventDefault()
  }

  const at = peaks.seconds ? Math.min(1, current / peaks.seconds) : 0
  return (
    <div
      ref={area}
      className={styles.strip}
      role="slider"
      tabIndex={0}
      aria-label="Position"
      aria-valuemin={0}
      aria-valuemax={Math.round(peaks.seconds)}
      aria-valuenow={Math.round(current)}
      aria-valuetext={`${clock(current)} of ${clock(peaks.seconds)}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onKeyDown={onKeyDown}
    >
      <canvas ref={canvas} className={styles.canvas} aria-hidden="true" />
      <span className={`small ${styles.voiceLabel}`}>Voice kept</span>
      <span className={`small ${styles.removedLabel}`}>Music removed</span>
      <div className={styles.playhead} style={{ left: `${at * 100}%` }} aria-hidden="true" />
    </div>
  )
}
