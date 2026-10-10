import { useCallback, useRef } from 'react'
import { paintLanes, useCanvas, type Peaks } from '../../lib/review/lanes'
import styles from './EmptyStrip.module.css'

/** A made-up minute of speech over a steady bed of music, in the shape a real file's peaks come in. */
function sampleTrace(): Peaks {
  const voice: number[] = []
  const removed: number[] = []
  for (let i = 0; i < 600; i++) {
    // Words: slow swells that open and close, each with a quick ripple inside it.
    const word = Math.max(0, Math.sin(i * 0.11) * Math.sin(i * 0.023 + 1))
    const speech = word * (0.6 + 0.4 * Math.abs(Math.sin(i * 0.9)))
    const bed = 0.5 + 0.3 * Math.sin(i * 0.37)
    voice.push(-speech, speech)
    removed.push(-bed, bed)
  }
  return { seconds: 60, voice, removed }
}

const TRACE = sampleTrace()

/** Where the labels sit, which the trace keeps clear of: the caption has its own room from 768 px. */
const clearOf = (width: number) => (width >= 768 ? 72 : 34)

/** Where the queue will be: the strip every file gets, with a faint trace and nothing in it yet. */
export function EmptyStrip({ dragging }: { dragging: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const paint = useCallback((ctx: CanvasRenderingContext2D, width: number, height: number) => {
    const top = clearOf(width)
    const lane = Math.max(0, (height - 1) / 2 - top)
    if (canvas.current) paintLanes(ctx, canvas.current, TRACE, width, { top, lane, gap: 1, bar: 1, step: 2 })
  }, [])
  useCanvas(canvas, paint)
  return (
    <figure className={styles.strip} data-dragging={dragging || undefined}>
      <canvas ref={canvas} className={styles.ghost} aria-hidden="true" />
      <span className={`small ${styles.voice}`}>Voice kept</span>
      <span className={styles.line} />
      <span className={`small ${styles.removed}`}>Music removed</span>
      <figcaption className={`small ${styles.caption}`}>
        Each file you add gets a strip like this one, with the voice kept above the line and the music removed below it.
      </figcaption>
    </figure>
  )
}
