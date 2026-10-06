import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Transport } from './Transport'

afterEach(() => vi.useRealTimers())

function setup(original = false) {
  const props = { onPlay: vi.fn(), onPause: vi.fn(), onToggle: vi.fn(), onHold: vi.fn() }
  render(<Transport playing={false} current={65} duration={200} original={original} {...props} />)
  return props
}

describe('Transport', () => {
  it('shows the time and a play button', async () => {
    const props = setup()
    expect(screen.getByText('1:05')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Play' }))
    expect(props.onPlay).toHaveBeenCalledOnce()
  })

  it('has a real switch for the original', () => {
    setup(true)
    const sw = screen.getByRole('switch', { name: 'Play the original (hold C)' })
    expect(sw).toHaveAttribute('aria-checked', 'true')
  })

  it('toggles on a click and on Space', async () => {
    const props = setup()
    const sw = screen.getByRole('switch')
    await userEvent.click(sw)
    expect(props.onToggle).toHaveBeenCalledTimes(1)
    sw.focus()
    await userEvent.keyboard(' ')
    expect(props.onToggle).toHaveBeenCalledTimes(2)
    expect(props.onHold).not.toHaveBeenCalled()
  })

  it('toggles from a screen reader, which sends a bare click', () => {
    const props = setup()
    screen.getByRole('switch').click()
    expect(props.onToggle).toHaveBeenCalledOnce()
  })

  it('plays the original only while the switch is held', () => {
    vi.useFakeTimers()
    const props = setup()
    const sw = screen.getByRole('switch')
    fireEvent.pointerDown(sw)
    act(() => vi.advanceTimersByTime(400))
    expect(props.onHold).toHaveBeenLastCalledWith(true)
    fireEvent.pointerUp(sw)
    expect(props.onHold).toHaveBeenLastCalledWith(false)
    expect(props.onToggle).not.toHaveBeenCalled()
  })

  it('ends a hold when the pointer is let go somewhere else', () => {
    vi.useFakeTimers()
    const props = setup()
    const sw = screen.getByRole('switch')
    fireEvent.pointerDown(sw)
    act(() => vi.advanceTimersByTime(400))
    fireEvent(sw, new Event('lostpointercapture', { bubbles: true }))
    expect(props.onHold).toHaveBeenLastCalledWith(false)
    expect(props.onToggle).not.toHaveBeenCalled()
  })

  it('ignores a right click and still answers the keyboard after a canceled press', async () => {
    const props = setup()
    const sw = screen.getByRole('switch')
    fireEvent.pointerDown(sw, { button: 2 })
    fireEvent.pointerUp(sw, { button: 2 })
    expect(props.onToggle).not.toHaveBeenCalled()
    fireEvent.pointerDown(sw, { button: 0 })
    fireEvent.pointerCancel(sw)
    sw.focus()
    await userEvent.keyboard('{Enter}')
    expect(props.onToggle).toHaveBeenCalledOnce()
  })

  it('flips once when Enter is held down', () => {
    const props = setup()
    const sw = screen.getByRole('switch')
    fireEvent.keyDown(sw, { key: 'Enter' })
    sw.click()
    const repeat = fireEvent.keyDown(sw, { key: 'Enter', repeat: true })
    // false: the repeat's default action, another click, was prevented.
    expect(repeat).toBe(false)
    expect(props.onToggle).toHaveBeenCalledOnce()
  })
})
