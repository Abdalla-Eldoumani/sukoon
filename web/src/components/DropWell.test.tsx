import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DropWell } from './DropWell'

describe('DropWell', () => {
  it('invites a drop and offers a button for people who do not drag', () => {
    render(<DropWell compact={false} dragging={false} onFiles={() => {}} />)
    expect(screen.getByText('Drop audio or video here')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose files' })).toBeInTheDocument()
  })

  it('says release while files are over the window', () => {
    render(<DropWell compact={false} dragging onFiles={() => {}} />)
    expect(screen.getByText('Release to add')).toBeInTheDocument()
  })

  it('hands chosen files over', async () => {
    const onFiles = vi.fn()
    const { container } = render(<DropWell compact={false} dragging={false} onFiles={onFiles} />)
    const file = new File(['x'], 'talk.mp3', { type: 'audio/mpeg' })
    await userEvent.upload(container.querySelector('input[type=file]') as HTMLInputElement, file)
    expect(onFiles).toHaveBeenCalledWith([file])
  })
})
