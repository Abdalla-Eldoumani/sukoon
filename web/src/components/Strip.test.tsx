import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Strip } from './Strip'

const peaks = { seconds: 200, voice: Array(4000).fill(0.2), removed: Array(4000).fill(-0.1) }

describe('Strip', () => {
  it('is a labelled position slider with both lanes named', () => {
    render(<Strip peaks={peaks} current={65} onSeek={() => {}} />)
    const slider = screen.getByRole('slider', { name: 'Position' })
    expect(slider).toHaveAttribute('aria-valuetext', '1:05 of 3:20')
    expect(screen.getByText('Voice')).toBeInTheDocument()
    expect(screen.getByText('Removed')).toBeInTheDocument()
  })

  it('moves five seconds with the arrow keys', async () => {
    const onSeek = vi.fn()
    render(<Strip peaks={peaks} current={60} onSeek={onSeek} />)
    screen.getByRole('slider').focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(onSeek).toHaveBeenLastCalledWith(65)
    await userEvent.keyboard('{ArrowLeft}')
    expect(onSeek).toHaveBeenLastCalledWith(55)
  })

  it('seeks to where it is clicked and follows a drag', () => {
    const onSeek = vi.fn()
    render(<Strip peaks={peaks} current={0} onSeek={onSeek} />)
    const slider = screen.getByRole('slider')
    slider.getBoundingClientRect = () => ({ left: 100, width: 400, top: 0, height: 133, right: 500, bottom: 133, x: 100, y: 0, toJSON: () => ({}) })
    let captured = false
    slider.setPointerCapture = () => {
      captured = true
    }
    slider.hasPointerCapture = () => captured
    fireEvent.pointerDown(slider, { clientX: 200, pointerId: 1 })
    expect(onSeek).toHaveBeenLastCalledWith(50)
    fireEvent.pointerMove(slider, { clientX: 400, pointerId: 1 })
    expect(onSeek).toHaveBeenLastCalledWith(150)
    fireEvent.pointerDown(slider, { clientX: 900, pointerId: 1 })
    expect(onSeek).toHaveBeenLastCalledWith(200)
  })
})
