import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { job } from '../test/fixtures'
import { ReviewPanel } from './ReviewPanel'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ seconds: 30, voice: [0, 0.2], removed: [-0.1, 0] }))),
  )
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(async () => {})
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ReviewPanel', () => {
  it('holding C plays the original and letting go returns to the clean voice', async () => {
    const { container } = render(<ReviewPanel job={job({ state: 'done' })} />)
    await screen.findByRole('slider')
    const [clean, original] = container.querySelectorAll('audio')
    const sw = screen.getByRole('switch')
    expect(sw).toHaveAttribute('aria-checked', 'false')
    expect(clean.muted).toBe(false)
    expect(original.muted).toBe(true)
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c' }))
    })
    expect(sw).toHaveAttribute('aria-checked', 'true')
    expect(clean.muted).toBe(true)
    expect(original.muted).toBe(false)
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keyup', { key: 'c' }))
    })
    expect(sw).toHaveAttribute('aria-checked', 'false')
    expect(clean.muted).toBe(false)
  })

  it('ignores copy shortcuts and lets go when the window loses focus', async () => {
    render(<ReviewPanel job={job({ state: 'done' })} />)
    await screen.findByRole('slider')
    const sw = screen.getByRole('switch')
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', metaKey: true }))
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true }))
    })
    expect(sw).toHaveAttribute('aria-checked', 'false')
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c' }))
    })
    expect(sw).toHaveAttribute('aria-checked', 'true')
    act(() => {
      window.dispatchEvent(new Event('blur'))
    })
    expect(sw).toHaveAttribute('aria-checked', 'false')
  })

  it('shows the video above the strip, muted, for a video job', async () => {
    const { container } = render(<ReviewPanel job={job({ state: 'done', kind: 'video', offset: 0.5 })} />)
    await screen.findByRole('slider')
    const video = container.querySelector('video')!
    expect(video).toHaveAttribute('src', '/api/jobs/a1/source')
    expect(video.muted).toBe(true)
  })

  it('falls back to the strip when the browser cannot play the video', async () => {
    const { container } = render(<ReviewPanel job={job({ state: 'done', kind: 'video' })} />)
    await screen.findByRole('slider')
    fireEvent.error(container.querySelector('video')!)
    expect(container.querySelector('video')).toBeNull()
    expect(screen.getByText(/Your browser can.t preview this video; the downloaded file is fine\./)).toBeInTheDocument()
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })
})
