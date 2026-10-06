import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

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
    const { container } = render(<App />)
    const enter = new Event('dragenter', { cancelable: true }) as DragEvent
    Object.defineProperty(enter, 'dataTransfer', { value: { types: ['Files'], files: [] } })
    window.dispatchEvent(enter)
    return vi.waitFor(() => {
      expect(screen.getByText('Release to add')).toBeInTheDocument()
      expect(container.ownerDocument.querySelector('[aria-hidden="true"][class*="frame"]')).not.toBeNull()
    })
  })
})
