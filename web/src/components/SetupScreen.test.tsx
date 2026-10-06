import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SetupScreen } from './SetupScreen'

describe('SetupScreen', () => {
  it('gives the install command and a way to check again', async () => {
    const onCheck = vi.fn()
    render(<SetupScreen install="winget install Gyan.FFmpeg" checking={false} onCheck={onCheck} />)
    expect(screen.getByRole('heading', { name: 'sukoon needs ffmpeg' })).toBeInTheDocument()
    expect(screen.getByText('winget install Gyan.FFmpeg')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Check again' }))
    expect(onCheck).toHaveBeenCalledOnce()
  })
})
