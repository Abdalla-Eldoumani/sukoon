import { useEffect, useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { clock } from '../format'
import styles from './Strip.module.css'

export interface Peaks {
  seconds: number
  voice: number[]
  removed: number[]
}

const RULER = 20
const LANE = 56
const STEP_S = 5
const DRAW_IN_MS = 400

interface Props {
  peaks: Peaks
  current: number
  onSeek: (seconds: number) => void
}

function css(el: Element, name: string): string {
  return getComputedStyle(el).getPropertyValue(name).trim()
}

function reducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** Draws both lanes and the ruler, up to `reveal` (0..1) of the width. */
function draw(canvas: HTMLCanvasElement, peaks: Peaks, reveal: number) {
  const ratio = window.devicePixelRatio || 1
  const width = canvas.clientWidth
  const height = RULER + LANE * 2 + 1
  canvas.width = Math.round(width * ratio)
  canvas.height = Math.round(height * ratio)
  let ctx: CanvasRenderingContext2D | null = null
  try {
    ctx = canvas.getContext('2d')
  } catch {
    ctx = null
  }
  if (!ctx || width === 0) return
  ctx.scale(ratio, ratio)
  ctx.clearRect(0, 0, width, height)

  ctx.fillStyle = css(canvas, '--raised')
  ctx.fillRect(0, RULER, width, LANE * 2 + 1)
  ctx.fillStyle = css(canvas, '--rule')
  ctx.fillRect(0, RULER + LANE, width, 1)

  // Up to ten ticks, one label per 80px so they never run into each other on a narrow window.
  const ticks = Math.min(10, Math.max(2, Math.floor(width / 80)))
  ctx.fillStyle = css(canvas, '--text-3')
  ctx.font = `450 11px ${css(canvas, '--font-mono')}`
  ctx.textBaseline = 'top'
  for (let i = 0; i < ticks; i++) {
    const x = Math.round((i / ticks) * width)
    ctx.fillRect(x, RULER - 6, 1, 6)
    if (i > 0) ctx.fillText(clock((i / ticks) * peaks.seconds), x + 3, 2)
  }

  const buckets = peaks.voice.length / 2
  const shown = Math.floor(buckets * reveal)
  // Both lanes share one scale, set by the louder of the two, so their sizes compare honestly.
  const loudest = Math.max(1e-6, ...peaks.voice.map(Math.abs), ...peaks.removed.map(Math.abs))
  const lane = (values: number[], color: string, center: number, direction: 1 | -1) => {
    ctx.fillStyle = color
    for (let i = 0; i < shown; i++) {
      const x = (i / buckets) * width
      const w = Math.max(1, width / buckets)
      // Each slice's loudest swing, so a lane reads as a level meter.
      const level = Math.min(1, Math.max(Math.abs(values[2 * i]), Math.abs(values[2 * i + 1])) / loudest)
      const h = Math.max(level * (LANE - 4), level > 0 ? 1 : 0)
      ctx.fillRect(x, direction === 1 ? center - h : center, w, h)
    }
  }
  lane(peaks.voice, css(canvas, '--voice'), RULER + LANE, 1)
  lane(peaks.removed, css(canvas, '--removed'), RULER + LANE + 1, -1)
}

export function Strip({ peaks, current, onSeek }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const area = useRef<HTMLDivElement>(null)
  const drawn = useRef(false)

  useEffect(() => {
    const el = canvas.current
    if (!el) return
    let frame = 0
    // The one flourish: the strip draws in once, left to right.
    if (!drawn.current && !reducedMotion() && typeof requestAnimationFrame === 'function') {
      const start = performance.now()
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / DRAW_IN_MS)
        draw(el, peaks, 1 - (1 - t) ** 3)
        if (t < 1) frame = requestAnimationFrame(step)
      }
      frame = requestAnimationFrame(step)
    } else {
      draw(el, peaks, 1)
    }
    drawn.current = true
    const redraw = () => draw(el, peaks, 1)
    const resize = typeof ResizeObserver === 'function' ? new ResizeObserver(redraw) : null
    resize?.observe(el)
    const themes = new MutationObserver(redraw)
    themes.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const scheme = window.matchMedia?.('(prefers-color-scheme: dark)')
    scheme?.addEventListener('change', redraw)
    return () => {
      cancelAnimationFrame(frame)
      resize?.disconnect()
      themes.disconnect()
      scheme?.removeEventListener('change', redraw)
    }
  }, [peaks])

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
      <span className={`label ${styles.voiceLabel}`}>Voice</span>
      <span className={`label ${styles.removedLabel}`}>Removed</span>
      <div className={styles.playhead} style={{ left: `${at * 100}%` }} aria-hidden="true" />
    </div>
  )
}
