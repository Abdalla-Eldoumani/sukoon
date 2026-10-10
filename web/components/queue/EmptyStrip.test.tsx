import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EmptyStrip } from './EmptyStrip'

function stubCanvas(width: number, height: number) {
  const bars: { x: number; y: number; w: number; h: number }[] = []
  const ctx = {
    scale: () => {},
    clearRect: () => {},
    fillRect: (x: number, y: number, w: number, h: number) => bars.push({ x, y, w, h }),
    fillStyle: '',
  }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(width)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(height)
  return bars
}

afterEach(() => vi.restoreAllMocks())

describe('EmptyStrip', () => {
  it('draws a trace in both lanes and keeps it clear of the labels', () => {
    const bars = stubCanvas(1200, 340)
    render(<EmptyStrip dragging={false} />)
    expect(bars.length).toBeGreaterThan(50)
    const centre = (340 - 1) / 2
    expect(bars.some((b) => b.y + b.h <= centre + 1)).toBe(true)
    expect(bars.some((b) => b.y >= centre + 1)).toBe(true)
    // Nothing reaches the 72 px at the top and bottom that the labels and the caption use.
    expect(Math.min(...bars.map((b) => b.y))).toBeGreaterThanOrEqual(72)
    expect(Math.max(...bars.map((b) => b.y + b.h))).toBeLessThanOrEqual(340 - 72 + 1)
  })

  it('draws nothing where the strip has no room beyond its labels', () => {
    const bars = stubCanvas(1200, 140)
    render(<EmptyStrip dragging={false} />)
    expect(bars).toHaveLength(0)
  })

  it('hides the trace from assistive technology', () => {
    const { container } = render(<EmptyStrip dragging={false} />)
    expect(container.querySelector('canvas')).toHaveAttribute('aria-hidden', 'true')
  })
})
