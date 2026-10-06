import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { FakeEventSource, job, model } from './test/fixtures'

beforeEach(() => vi.stubGlobal('EventSource', FakeEventSource))
afterEach(() => vi.unstubAllGlobals())

function serveHealth(device: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify({ status: 'ok', version: '0.1.0', device }), {
        headers: { 'content-type': 'application/json' },
      }),
    ),
  )
}

describe('App', () => {
  it('shows the empty state with the plain promise', () => {
    serveHealth('CPU')
    render(<App />)
    expect(screen.getByText('sukoon')).toBeInTheDocument()
    expect(screen.getByText(/Voices stay\. Instruments, and most other non-voice sounds/)).toBeInTheDocument()
  })

  it('shows the device the server reports', async () => {
    serveHealth('CUDA · RTX 3060 Laptop')
    render(<App />)
    expect(await screen.findByText('CUDA · RTX 3060 Laptop')).toBeInTheDocument()
  })

  it('frames the window while files are dragged over it', () => {
    serveHealth('CPU')
    render(<App />)
    const enter = new Event('dragenter', { cancelable: true }) as DragEvent
    Object.defineProperty(enter, 'dataTransfer', { value: { types: ['Files'], files: [] } })
    window.dispatchEvent(enter)
    return vi.waitFor(() => {
      expect(screen.getByText('Release to add')).toBeInTheDocument()
      expect(screen.getByTestId('drag-frame')).toBeInTheDocument()
    })
  })

  it('lists jobs from the event stream and follows their changes', async () => {
    serveHealth('CPU')
    render(<App />)
    act(() => FakeEventSource.last!.emit('snapshot', { jobs: [job({ state: 'queued' })], models: [] }))
    expect(screen.getByText('Queued')).toBeInTheDocument()
    act(() => FakeEventSource.last!.emit('job', job({ state: 'separating', progress: 0.5 })))
    expect(screen.getByText('Separating')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
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
})
