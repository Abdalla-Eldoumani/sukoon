import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { FakeEventSource, job, model } from '../test/fixtures'

const health = { status: 'ok', version: '0.1.0', device: 'CPU', ffmpeg: { ok: true, install: '' } }
const settings = { preset: 'best', device: 'auto', audio_format: null, video_format: null, missing: {}, folder: '/data' }

beforeEach(() => {
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.endsWith('/health')
        ? health
        : url.endsWith('/settings')
          ? settings
          : url.endsWith('/peaks')
            ? { seconds: 30, voice: [0, 0.2], removed: [-0.1, 0] }
            : { jobs: 1000, models: 0 }
      return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })
    }),
  )
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(async () => {})
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function seriousViolations() {
  const results = await axe.run(document.body, { resultTypes: ['violations'] })
  return results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

describe('accessibility', () => {
  it('the empty state has no serious problems', async () => {
    render(<App />)
    await screen.findByText('CPU')
    expect(await seriousViolations()).toEqual([])
  })

  it('a running queue has no serious problems', async () => {
    render(<App />)
    act(() =>
      FakeEventSource.last!.emit('snapshot', {
        jobs: [
          job({ id: 'a', state: 'separating', progress: 0.4, eta: 90 }),
          job({ id: 'b', name: 'two.mkv', kind: 'video', state: 'awaiting_track', tracks: [{ language: 'eng', title: null, channels: 2, default: true }], formats: [{ value: 'mkv', video: true, reencode: false, missing: null }], options: { preset: 'best', format: 'mkv', track: null } }),
          job({ id: 'c', name: 'bad.mp4', state: 'failed', retryable: false, error: "This file isn't audio or video sukoon can read." }),
          job({ id: 'd', name: 'done.mp3', state: 'done', progress: 1, output_name: 'done (no music).mp3' }),
        ],
        models: [model(), model({ preset: 'fast', size: 66_762_490 })],
      }),
    )
    expect(await seriousViolations()).toEqual([])
  })

  it('the review panel has no serious problems', async () => {
    render(<App />)
    act(() =>
      FakeEventSource.last!.emit('snapshot', {
        jobs: [job({ id: 'd', name: 'done.mp3', state: 'done', progress: 1, output_name: 'done (no music).mp3' })],
        models: [],
      }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Review done.mp3' }))
    await screen.findByRole('slider')
    expect(await seriousViolations()).toEqual([])
  })

  it('the settings sheet has no serious problems', async () => {
    render(<App />)
    await screen.findByText('CPU')
    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
    await screen.findByRole('dialog')
    expect(await seriousViolations()).toEqual([])
  })
})
