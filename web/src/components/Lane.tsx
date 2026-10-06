import { useCallback, useEffect, useRef, useState } from 'react'
import { loadPeaks, paintLanes, useCanvas, type Peaks } from '../lanes'
import type { Job } from '../types'
import styles from './Lane.module.css'

const MOVING = new Set(['uploading', 'decoding', 'separating', 'encoding'])

/** How far a job has got, 0 to 1, when that is known. */
export function position(job: Job): number | null {
  if (job.state === 'fetching') return job.link?.total ? job.link.done / job.link.total : null
  return MOVING.has(job.state) ? job.progress : null
}

function MiniStrip({ peaks, drawIn }: { peaks: Peaks; drawIn: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const paint = useCallback(
    (ctx: CanvasRenderingContext2D, width: number, height: number) => {
      const lane = (height - 1) / 2
      paintLanes(ctx, canvas.current!, peaks, width, { top: 0, lane, gap: 1, bar: 1, step: 2 })
    },
    [peaks],
  )
  useCanvas(canvas, paint)
  return (
    <div className={styles.lane}>
      <canvas ref={canvas} className={styles.canvas} />
      {drawIn && <div className={styles.cover} />}
    </div>
  )
}

/** The row's own strip: what was kept and removed once done, how far it has got while working. */
export function Lane({ job, drawIn = false, className = '' }: { job: Job; drawIn?: boolean; className?: string }) {
  const cleaned = job.state === 'done' && !job.options.keep_music
  const [peaks, setPeaks] = useState<Peaks | null>(null)
  useEffect(() => {
    if (!cleaned) return
    let live = true
    loadPeaks(job.id).then(
      (p) => live && setPeaks(p),
      () => {},
    )
    return () => {
      live = false
    }
  }, [cleaned, job.id])

  if (cleaned && peaks) {
    return (
      <div className={`${styles.cell} ${className}`} aria-hidden="true">
        <MiniStrip peaks={peaks} drawIn={drawIn} />
      </div>
    )
  }
  const at = position(job)
  return (
    <div className={`${styles.cell} ${className}`} aria-hidden="true">
      <div className={styles.line}>
        {at !== null && <div className={styles.done} style={{ transform: `translateX(${at * 100}%)` }} />}
      </div>
    </div>
  )
}
