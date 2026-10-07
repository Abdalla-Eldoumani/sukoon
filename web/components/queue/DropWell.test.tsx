import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DropWell } from './DropWell'

const noLink = async () => true

describe('DropWell', () => {
  it('invites a drop and offers a button for people who do not drag', () => {
    render(<DropWell compact={false} dragging={false} onFiles={() => {}} onLink={noLink} />)
    expect(screen.getByRole('heading', { name: 'Drop a recording anywhere.' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose files' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Link to a video' })).toBeInTheDocument()
  })

  it('shows the empty strip the files will fill, and the sites links work from', () => {
    render(<DropWell compact={false} dragging={false} onFiles={() => {}} onLink={noLink} />)
    expect(screen.getByText('Voice kept')).toBeInTheDocument()
    expect(screen.getByText('Music removed')).toBeInTheDocument()
    expect(screen.getByText(/Links work from YouTube, X, Instagram, TikTok/)).toBeInTheDocument()
  })

  it('says release, and inks the strip line, while files are over the window', () => {
    const { container } = render(<DropWell compact={false} dragging onFiles={() => {}} onLink={noLink} />)
    expect(screen.getByText('Release to add.')).toBeInTheDocument()
    expect(container.querySelector('figure')).toHaveAttribute('data-dragging')
  })

  it('hands chosen files over', async () => {
    const onFiles = vi.fn()
    const { container } = render(<DropWell compact={false} dragging={false} onFiles={onFiles} onLink={noLink} />)
    const file = new File(['x'], 'talk.mp3', { type: 'audio/mpeg' })
    await userEvent.upload(container.querySelector('input[type=file]') as HTMLInputElement, file)
    expect(onFiles).toHaveBeenCalledWith([file])
  })

  it('adds a pasted link and clears the field once it is a job', async () => {
    const onLink = vi.fn(async () => true)
    render(<DropWell compact={false} dragging={false} onFiles={() => {}} onLink={onLink} />)
    const field = screen.getByRole('textbox', { name: 'Link to a video' })
    await userEvent.type(field, 'https://youtu.be/jNQXAC9IVRw{Enter}')
    expect(onLink).toHaveBeenCalledWith('https://youtu.be/jNQXAC9IVRw')
    expect(field).toHaveValue('')
  })

  it('keeps a refused link in the field with the reason under it', async () => {
    const reason = 'sukoon takes links from YouTube, X, Instagram, TikTok, Facebook, Reddit, Vimeo, and SoundCloud.'
    const { rerender } = render(
      <DropWell compact={false} dragging={false} onFiles={() => {}} onLink={async () => false} />,
    )
    const field = screen.getByRole('textbox', { name: 'Link to a video' })
    await userEvent.type(field, 'https://example.com/v')
    await userEvent.click(screen.getByRole('button', { name: 'Add link' }))
    rerender(
      <DropWell compact={false} dragging={false} onFiles={() => {}} onLink={async () => false} linkError={reason} />,
    )
    expect(field).toHaveValue('https://example.com/v')
    expect(field).toHaveAccessibleDescription(reason)
    expect(field).toHaveAttribute('aria-invalid', 'true')
  })
})
