import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { job } from '../test/fixtures'
import { JobChoices } from './JobChoices'

const VIDEO_FORMATS = [
  { value: 'mp4', video: true, reencode: false },
  { value: 'mkv', video: true, reencode: false },
  { value: 'webm', video: true, reencode: true },
  { value: 'mp3', video: false, reencode: false },
]

let posted: { url: string; body: unknown }[]

beforeEach(() => {
  posted = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      posted.push({ url, body: JSON.parse(String(init.body)) })
      return new Response('{}', { headers: { 'content-type': 'application/json' } })
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('JobChoices', () => {
  it('lets the listener pick the audio track, default first', async () => {
    render(
      <JobChoices
        job={job({
          state: 'awaiting_track',
          kind: 'video',
          tracks: [
            { language: 'eng', title: 'Main', channels: 2 },
            { language: 'ara', title: 'Commentary', channels: 6 },
          ],
        })}
      />,
    )
    const select = screen.getByRole('combobox', { name: 'Audio track for lecture.mp3' })
    expect(select).toHaveDisplayValue('Track 1 · eng · Main · stereo')
    await userEvent.selectOptions(select, 'Track 2 · ara · Commentary · 6 channels')
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(posted).toEqual([{ url: '/api/jobs/a1/choose', body: { track: 1 } }])
  })

  it('says a re-encode is coming and waits for consent', async () => {
    const confirm = 'The picture will be re-encoded to VP9 for WEBM (about as long as the video’s duration on this machine).'
    render(<JobChoices job={job({ state: 'awaiting_confirm', kind: 'video', confirm, formats: VIDEO_FORMATS, options: { preset: 'best', format: 'webm', track: null } })} />)
    expect(screen.getByText(confirm)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Re-encode' }))
    expect(posted[0].body).toEqual({ confirm: true })
  })

  it('marks formats that re-encode or drop the picture', async () => {
    render(<JobChoices job={job({ kind: 'video', formats: VIDEO_FORMATS, options: { preset: 'best', format: 'mp4', track: null } })} />)
    const select = screen.getByRole('combobox', { name: 'Output format for lecture.mp3' })
    expect(Array.from((select as HTMLSelectElement).options).map((o) => o.text)).toEqual([
      'MP4',
      'MKV',
      'WEBM (re-encodes the picture)',
      'MP3 (audio only)',
    ])
    await userEvent.selectOptions(select, 'MKV')
    expect(posted[0].body).toEqual({ format: 'mkv' })
  })

  it('offers nothing once the job is running', () => {
    const { container } = render(<JobChoices job={job({ state: 'separating', formats: VIDEO_FORMATS })} />)
    expect(container).toBeEmptyDOMElement()
  })
})
