import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Transport } from './Transport'

afterEach(() => vi.useRealTimers())

/** Holds the state the review panel would, so tests read what the user sees. */
function Harness({ startOriginal = false }: { startOriginal?: boolean }) {
  const [playing, setPlaying] = useState(false)
  const [original, setOriginal] = useState(startOriginal)
  const [held, setHeld] = useState(false)
  return (
    <>
      <Transport
        playing={playing}
        current={65}
        duration={200}
        original={original}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onToggle={() => setOriginal((o) => !o)}
        onHold={setHeld}
      />
      <output aria-label="hearing">{held || original ? 'original' : 'clean'}</output>
    </>
  )
}

const switchEl = () => screen.getByRole('switch')
const hearing = () => screen.getByLabelText('hearing').textContent

describe('Transport', () => {
  it('shows the time and plays and pauses', async () => {
    render(<Harness />)
    expect(screen.getByText('1:05')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Play' }))
    await userEvent.click(screen.getByRole('button', { name: 'Pause' }))
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument()
  })

  it('has a real switch for the original', () => {
    render(<Harness startOriginal />)
    expect(screen.getByRole('switch', { name: 'Play the original (hold C)' })).toHaveAttribute('aria-checked', 'true')
  })

  it('toggles on a click and on Space', async () => {
    render(<Harness />)
    await userEvent.click(switchEl())
    expect(switchEl()).toHaveAttribute('aria-checked', 'true')
    switchEl().focus()
    await userEvent.keyboard(' ')
    expect(switchEl()).toHaveAttribute('aria-checked', 'false')
  })

  it('toggles from a screen reader, which sends a bare click', () => {
    render(<Harness />)
    act(() => switchEl().click())
    expect(switchEl()).toHaveAttribute('aria-checked', 'true')
  })

  it('plays the original only while the switch is held', () => {
    vi.useFakeTimers()
    render(<Harness />)
    fireEvent.pointerDown(switchEl())
    act(() => vi.advanceTimersByTime(400))
    expect(hearing()).toBe('original')
    fireEvent.pointerUp(switchEl())
    expect(hearing()).toBe('clean')
    expect(switchEl()).toHaveAttribute('aria-checked', 'false')
  })

  it('ends a hold when the pointer is let go somewhere else', () => {
    vi.useFakeTimers()
    render(<Harness />)
    fireEvent.pointerDown(switchEl())
    act(() => vi.advanceTimersByTime(400))
    fireEvent(switchEl(), new Event('lostpointercapture', { bubbles: true }))
    expect(hearing()).toBe('clean')
    expect(switchEl()).toHaveAttribute('aria-checked', 'false')
  })

  it('ignores a right click and still answers the keyboard after a canceled press', async () => {
    render(<Harness />)
    fireEvent.pointerDown(switchEl(), { button: 2 })
    fireEvent.pointerUp(switchEl(), { button: 2 })
    expect(switchEl()).toHaveAttribute('aria-checked', 'false')
    fireEvent.pointerDown(switchEl(), { button: 0 })
    fireEvent.pointerCancel(switchEl())
    switchEl().focus()
    await userEvent.keyboard('{Enter}')
    expect(switchEl()).toHaveAttribute('aria-checked', 'true')
  })

  it('flips once when Enter is held down', () => {
    render(<Harness />)
    fireEvent.keyDown(switchEl(), { key: 'Enter' })
    act(() => switchEl().click())
    const repeat = fireEvent.keyDown(switchEl(), { key: 'Enter', repeat: true })
    // false: the repeat's default action, another click, was prevented.
    expect(repeat).toBe(false)
    expect(switchEl()).toHaveAttribute('aria-checked', 'true')
  })

  it('starts no hold after the panel closes mid-press', () => {
    vi.useFakeTimers()
    const onHold = vi.fn()
    const { unmount } = render(
      <Transport playing={false} current={0} duration={10} original={false} onPlay={() => {}} onPause={() => {}} onToggle={() => {}} onHold={onHold} />,
    )
    fireEvent.pointerDown(switchEl())
    unmount()
    act(() => vi.advanceTimersByTime(400))
    expect(onHold).not.toHaveBeenCalled()
  })
})
