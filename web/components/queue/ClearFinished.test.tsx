import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ClearFinished } from './ClearFinished'

describe('ClearFinished', () => {
  it('asks once, naming how many jobs, before it clears anything', async () => {
    const onClear = vi.fn()
    render(<ClearFinished count={3} error={null} onClear={onClear} />)
    await userEvent.click(screen.getByRole('button', { name: 'Clear finished' }))
    expect(screen.getByText('Clear 3 finished jobs and their files?')).toBeInTheDocument()
    expect(onClear).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(onClear).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Clear finished' })).toBeInTheDocument()
  })

  it('uses the singular for one job and puts the question away on Keep', async () => {
    const onClear = vi.fn()
    render(<ClearFinished count={1} error={null} onClear={onClear} />)
    await userEvent.click(screen.getByRole('button', { name: 'Clear finished' }))
    expect(screen.getByText('Clear 1 finished job and their files?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }))
    expect(screen.getByRole('button', { name: 'Clear finished' })).toBeInTheDocument()
    expect(onClear).not.toHaveBeenCalled()
  })

  it('shows why a clear failed', () => {
    render(<ClearFinished count={2} error="A job is still running." onClear={() => {}} />)
    expect(screen.getByText('A job is still running.')).toBeInTheDocument()
  })
})
