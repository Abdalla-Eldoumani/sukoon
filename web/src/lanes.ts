import { useEffect, type RefObject } from 'react'
import { getJson } from './api'

export interface Peaks {
  seconds: number
  voice: number[]
  removed: number[]
}

// ceiling: every finished row loads its peaks (about 60 KB) when the page opens; load them as rows
// scroll into view if queues of a few hundred finished jobs become normal.
const cache = new Map<string, Promise<Peaks>>()

/** A job's peaks, fetched once per page for the row and its review to share. */
export function loadPeaks(jobId: string): Promise<Peaks> {
  let found = cache.get(jobId)
  if (!found) {
    found = getJson<Peaks>(`/api/jobs/${jobId}/peaks`)
    found.catch(() => cache.delete(jobId))
    cache.set(jobId, found)
  }
  return found
}

export function cssVar(el: Element, name: string): string {
  return getComputedStyle(el).getPropertyValue(name).trim()
}

export function loudestOf(peaks: Peaks): number {
  let loudest = 1e-6
  for (const v of peaks.voice) loudest = Math.max(loudest, Math.abs(v))
  for (const v of peaks.removed) loudest = Math.max(loudest, Math.abs(v))
  return loudest
}

interface Lanes {
  top: number
  lane: number
  gap: number
  bar: number
  step: number
}

/** Voice above the gap, removed below it, both on one scale so their sizes compare honestly. */
export function paintLanes(ctx: CanvasRenderingContext2D, el: Element, peaks: Peaks, width: number, at: Lanes) {
  const loudest = loudestOf(peaks)
  const buckets = peaks.voice.length / 2
  const center = at.top + at.lane
  const level = (values: number[], x: number) => {
    const from = Math.floor((x / width) * buckets)
    const to = Math.max(from + 1, Math.floor(((x + at.step) / width) * buckets))
    let most = 0
    for (let i = from; i < to && i < buckets; i++) {
      most = Math.max(most, Math.abs(values[2 * i]), Math.abs(values[2 * i + 1]))
    }
    return Math.min(1, most / loudest)
  }
  const voice = cssVar(el, '--voice')
  const removed = cssVar(el, '--removed')
  for (let x = 0; x < width; x += at.step) {
    const v = level(peaks.voice, x) * at.lane
    const r = level(peaks.removed, x) * at.lane
    ctx.fillStyle = voice
    if (v >= 0.5) ctx.fillRect(x, center - v, at.bar, v)
    ctx.fillStyle = removed
    if (r >= 0.5) ctx.fillRect(x, center + at.gap, at.bar, r)
  }
}

/** Paints a canvas at the screen's pixel ratio, again on resize and on a theme change; pass a
 * memoised `paint` so it repaints only when what it draws changes. */
export function useCanvas(
  ref: RefObject<HTMLCanvasElement | null>,
  paint: (ctx: CanvasRenderingContext2D, width: number, height: number) => void,
) {
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const draw = () => {
      const ratio = window.devicePixelRatio || 1
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      let ctx: CanvasRenderingContext2D | null
      try {
        ctx = canvas.getContext('2d')
      } catch {
        ctx = null
      }
      if (!ctx || width === 0) return
      ctx.scale(ratio, ratio)
      ctx.clearRect(0, 0, width, height)
      paint(ctx, width, height)
    }
    draw()
    const resize = typeof ResizeObserver === 'function' ? new ResizeObserver(draw) : null
    resize?.observe(canvas)
    const themes = new MutationObserver(draw)
    themes.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const scheme = window.matchMedia?.('(prefers-color-scheme: dark)')
    scheme?.addEventListener('change', draw)
    return () => {
      resize?.disconnect()
      themes.disconnect()
      scheme?.removeEventListener('change', draw)
    }
  }, [ref, paint])
}
