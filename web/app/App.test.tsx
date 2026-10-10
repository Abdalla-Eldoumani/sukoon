import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { FakeEventSource, job, model } from '../test/fixtures'

beforeEach(() => vi.stubGlobal('EventSource', FakeEventSource))
afterEach(() => vi.unstubAllGlobals())

function serveHealth(device: string, ffmpeg = true) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.endsWith('/api/health')
        ? { status: 'ok', version: '0.1.0', device, ffmpeg: { ok: ffmpeg, install: 'sudo apt install ffmpeg' } }
        : { jobs: 0, models: 0 }
      return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })
    }),
  )
}

describe('App', () => {
  it('shows the empty state with the plain promise', () => {
    serveHealth('CPU')
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'sukoon سكون' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Drop a recording anywhere.' })).toBeInTheDocument()
    expect(screen.getByText('Voices stay and the music goes. Everything happens on this computer.')).toBeInTheDocument()
  })

  it('shows the device the server reports', async () => {
    serveHealth('CUDA · RTX 3060 Laptop')
    render(<App />)
    expect(await screen.findByText('RTX 3060 Laptop')).toBeInTheDocument()
    expect(screen.getByText('CUDA')).toBeInTheDocument()
  })

  it('frames the window while files are dragged over it', () => {
    serveHealth('CPU')
    render(<App />)
    const enter = new Event('dragenter', { cancelable: true }) as DragEvent
    Object.defineProperty(enter, 'dataTransfer', { value: { types: ['Files'], files: [] } })
    window.dispatchEvent(enter)
    return vi.waitFor(() => {
      expect(screen.getByText('Release to add.')).toBeInTheDocument()
      expect(screen.getByTestId('drag-frame')).toBeInTheDocument()
    })
  })

  it('lists jobs from the event stream and follows their changes', async () => {
    serveHealth('CPU')
    render(<App />)
    act(() => FakeEventSource.last!.emit('snapshot', { jobs: [job({ state: 'queued' })], models: [] }))
    expect(screen.getByText('Queued')).toBeInTheDocument()
    act(() => FakeEventSource.last!.emit('job', job({ state: 'separating', progress: 0.55, through: 0.5 })))
    expect(screen.getByText('Separating')).toBeInTheDocument()
    expect(screen.getByText('1:03 of 2:05')).toBeInTheDocument()
    act(() => FakeEventSource.last!.emit('deleted', { id: 'a1' }))
    expect(screen.queryByRole('list', { name: 'Queue' })).toBeNull()
  })

  it('shows the model card while a job waits for its model', () => {
    serveHealth('CPU')
    render(<App />)
    act(() =>
      FakeEventSource.last!.emit('snapshot', {
        jobs: [job({ state: 'waiting_model' })],
        models: [model(), model({ preset: 'fast', size: 66_762_490 })],
      }),
    )
    expect(screen.getByRole('button', { name: 'Download Best (913 MB)' })).toBeInTheDocument()
  })

  it('slides in only the rows that arrive after the page loaded', () => {
    serveHealth('CPU')
    render(<App />)
    act(() => FakeEventSource.last!.emit('snapshot', { jobs: [job({ id: 'old' })], models: [] }))
    act(() => FakeEventSource.last!.emit('job', job({ id: 'new', name: 'new.mp3', created: 2 })))
    const [old, added] = screen.getAllByRole('listitem')
    expect(old.className).not.toMatch(/arriving/)
    expect(added.className).toMatch(/arriving/)
  })

  it('shows an earlier job of the same name beside the file being uploaded', async () => {
    serveHealth('CPU')
    // An upload that never answers, so the file stays in flight for the whole test.
    vi.stubGlobal(
      'XMLHttpRequest',
      class {
        upload = {}
        open() {}
        send() {}
      },
    )
    const { container } = render(<App />)
    act(() =>
      FakeEventSource.last!.emit('snapshot', {
        jobs: [
          job({ id: 'earlier', name: 'talk.mp3', state: 'checking', created: 1 }),
          job({ id: 'sending', name: 'talk.mp3', state: 'checking', created: 2 }),
        ],
        models: [],
      }),
    )
    await userEvent.upload(
      container.querySelector('input[type=file]') as HTMLInputElement,
      new File(['x'], 'talk.mp3', { type: 'audio/mpeg' }),
    )
    // The server's copy of the file in flight is the local row; the earlier job is its own row.
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('shows only the setup screen while ffmpeg is missing', async () => {
    serveHealth('CPU', false)
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'sukoon needs ffmpeg.' })).toBeInTheDocument()
    expect(screen.queryByText('Drop a recording anywhere.')).toBeNull()
  })

  it('keeps a saved setting when an earlier change is refused afterwards', async () => {
    const stored = { preset: 'best', device: 'auto', audio_format: null, video_format: null, formats: { audio: ['mp3', 'm4a', 'wav', 'flac', 'opus', 'ogg'], video: ['mp4', 'mkv', 'webm', 'mov'] }, missing: {}, folder: '/data' }
    let refuse: (r: Response) => void = () => {}
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/api/health')) return json({ status: 'ok', version: '0.1.0', device: 'CPU', ffmpeg: { ok: true, install: '' } })
        if (!url.endsWith('/api/settings')) return json({ jobs: 0, models: 0 })
        if (init?.method !== 'PUT') return json(stored)
        const change = JSON.parse(String(init.body)) as Record<string, string>
        // The quality change is held and refused later; the device change saves at once.
        if ('preset' in change) return new Promise<Response>((resolve) => (refuse = resolve))
        Object.assign(stored, change)
        return json(stored)
      }),
    )
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Settings' }, { timeout: 2000 }))
    await userEvent.click(screen.getByRole('radio', { name: 'Fast' }))
    await userEvent.click(screen.getByRole('radio', { name: 'CPU' }))
    await waitFor(() => expect(screen.getByRole('radio', { name: 'CPU' })).toHaveAttribute('aria-checked', 'true'))
    await act(async () => refuse(json({ detail: 'Could not save.' }, 500)))
    expect(await screen.findByText('Could not save.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Best' })).toHaveAttribute('aria-checked', 'true'))
    expect(screen.getByRole('radio', { name: 'CPU' })).toHaveAttribute('aria-checked', 'true')
  })

  it('says so when the server refuses to start a model download', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        const json = (body: unknown, status = 200) =>
          new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
        if (url.includes('/download')) return json({ error: 'A download is already running.' }, 409)
        if (url.endsWith('/api/health')) return json({ status: 'ok', version: '0.1.0', device: 'CPU', ffmpeg: { ok: true, install: '' } })
        if (url.endsWith('/api/settings') && init?.method !== 'PUT') {
          return json({ preset: 'best', device: 'auto', audio_format: null, video_format: null, formats: { audio: ['mp3', 'm4a', 'wav', 'flac', 'opus', 'ogg'], video: ['mp4', 'mkv', 'webm', 'mov'] }, missing: {}, folder: '/data' })
        }
        return json({ jobs: 0, models: 0 })
      }),
    )
    render(<App />)
    act(() =>
      FakeEventSource.last!.emit('snapshot', {
        jobs: [job({ state: 'waiting_model' })],
        models: [model({ preset: 'best' }), model({ preset: 'fast' })],
      }),
    )
    await userEvent.click(screen.getByRole('button', { name: /Download Best/ }))
    expect(await screen.findByText('A download is already running.')).toBeInTheDocument()
  })

  it('starts a link job when a link is pasted anywhere but a text field', async () => {
    const sent: string[] = []
    serveLinks(sent, () => new Response(JSON.stringify(job({ state: 'fetching' })), { status: 201 }))
    render(<App />)
    paste(document.body, 'https://youtu.be/jNQXAC9IVRw')
    await waitFor(() => expect(sent).toEqual(['https://youtu.be/jNQXAC9IVRw']))
  })

  it('leaves a paste into a text field to the field', async () => {
    const sent: string[] = []
    serveLinks(sent, () => new Response('{}', { status: 201 }))
    render(<App />)
    paste(screen.getByRole('textbox', { name: 'Link to a video' }), 'https://youtu.be/jNQXAC9IVRw')
    paste(document.body, 'just some words')
    await new Promise((r) => setTimeout(r, 50))
    expect(sent).toEqual([])
  })

  it('says why a pasted link was refused', async () => {
    const reason = 'sukoon takes links from YouTube, X, Instagram, TikTok, Facebook, Reddit, Vimeo, and SoundCloud.'
    serveLinks([], () => new Response(JSON.stringify({ error: reason }), { status: 400 }))
    render(<App />)
    paste(document.body, 'https://example.com/video')
    expect(await screen.findByText(reason)).toBeInTheDocument()
  })
})

function paste(target: Element, text: string) {
  const event = new Event('paste', { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'clipboardData', { value: { getData: () => text } })
  target.dispatchEvent(event)
}

/** Health and settings as usual; each link the page sends is recorded and answered. */
function serveLinks(sent: string[], answer: () => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/links') {
        sent.push((JSON.parse(String(init?.body)) as { url: string }).url)
        return answer()
      }
      const body = url.endsWith('/api/health')
        ? { status: 'ok', version: '0.1.0', device: 'CPU', ffmpeg: { ok: true, install: '' } }
        : { jobs: 0, models: 0 }
      return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })
    }),
  )
}
