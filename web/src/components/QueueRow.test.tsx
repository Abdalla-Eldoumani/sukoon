import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { job } from '../test/fixtures'
import { QueueRow } from './QueueRow'

function row(fields: Parameters<typeof job>[0], problem: string | null = null) {
  const actions = { cancel: vi.fn(), retry: vi.fn(), remove: vi.fn() }
  render(
    <ul>
      <QueueRow job={job(fields)} actions={actions} problem={problem} />
    </ul>,
  )
  return actions
}

describe('QueueRow', () => {
  it('shows the stage and percentage while separating', () => {
    row({ state: 'separating', progress: 0.42 })
    expect(screen.getByText('Separating')).toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.getByText('2:05')).toBeInTheDocument()
    expect(screen.getByRole('listitem', { name: 'lecture.mp3' })).toHaveAttribute('aria-description', 'Separating, 42%')
  })

  it('offers the download when done, under the output name', () => {
    row({ state: 'done', progress: 1, output_name: 'lecture (no music).mp3' })
    const link = screen.getByRole('link', { name: 'Download lecture (no music).mp3' })
    expect(link).toHaveAttribute('href', '/api/jobs/a1/output')
    expect(link).toHaveAttribute('download', 'lecture (no music).mp3')
  })

  it('puts the reason for a failure under the name', () => {
    row({ state: 'failed', error: "This file isn't audio or video sukoon can read." })
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText("This file isn't audio or video sukoon can read.")).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('shows notes on a finished job', () => {
    row({ state: 'done', notes: ['Surround was mixed down to stereo.'], output_name: 'x.mp4' })
    expect(screen.getByText('Surround was mixed down to stereo.')).toBeInTheDocument()
  })

  it('names the waiting states plainly', () => {
    row({ state: 'waiting_model' })
    expect(screen.getByText('Waiting for model')).toBeInTheDocument()
  })

  it('keeps the full name in the title when it is cut', () => {
    const name = `${'very long episode title '.repeat(4)}12.mkv`
    row({ name, kind: 'video' })
    expect(screen.getByTitle(name).textContent).toContain('…')
  })

  it('shows the time left once the server has an estimate', () => {
    row({ state: 'separating', progress: 0.3, eta: 134 })
    expect(screen.getByTitle('Time left')).toHaveTextContent('2:14')
  })

  it('cancels a running job', async () => {
    const actions = row({ state: 'separating', progress: 0.3 })
    await userEvent.click(screen.getByRole('button', { name: 'Cancel lecture.mp3' }))
    expect(actions.cancel).toHaveBeenCalledWith(expect.objectContaining({ name: 'lecture.mp3' }))
    expect(screen.queryByRole('button', { name: /Delete/ })).toBeNull()
  })

  it('offers retry and delete after a failure', async () => {
    const actions = row({ state: 'interrupted' })
    await userEvent.click(screen.getByRole('button', { name: 'Retry lecture.mp3' }))
    expect(actions.retry).toHaveBeenCalledWith(expect.objectContaining({ name: 'lecture.mp3' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete lecture.mp3' }))
    expect(actions.remove).toHaveBeenCalledWith(expect.objectContaining({ name: 'lecture.mp3' }))
  })

  it('does not delete on the second click of a double click', () => {
    // A queued job stops at once, so Delete is under the pointer before a double click on Cancel ends.
    const actions = row({ state: 'canceled' })
    fireEvent.click(screen.getByRole('button', { name: 'Delete lecture.mp3' }), { detail: 2 })
    expect(actions.remove).not.toHaveBeenCalled()
  })

  it('does not offer retry for a file that was rejected', () => {
    row({ state: 'failed', retryable: false, error: 'This is a playlist, not a media file.' })
    expect(screen.queryByRole('button', { name: /Retry/ })).toBeNull()
  })

  it('asks before deleting a finished job', async () => {
    const actions = row({ state: 'done', output_name: 'lecture (no music).mp3' })
    await userEvent.click(screen.getByRole('button', { name: 'Delete lecture.mp3' }))
    expect(actions.remove).not.toHaveBeenCalled()
    expect(screen.getByText('Delete this job and its cleaned file?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }))
    expect(screen.queryByText('Delete this job and its cleaned file?')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Delete lecture.mp3' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(actions.remove).toHaveBeenCalledWith(expect.objectContaining({ name: 'lecture.mp3' }))
  })

  it('shows why an action failed', () => {
    row({ state: 'separating' }, 'Cancel this job before deleting it.')
    expect(screen.getByText('Cancel this job before deleting it.')).toBeInTheDocument()
  })

  it('says where a link comes from and how much has arrived', () => {
    row({ state: 'fetching', progress: 0.3, name: 'youtu.be/jNQXAC9IVRw', link: { url: 'https://youtu.be/jNQXAC9IVRw', site: 'youtu.be', done: 12_000_000, total: 40_000_000 } })
    expect(screen.getByText('Fetching')).toBeInTheDocument()
    expect(screen.getByText('from youtu.be · 12 MB of 40 MB')).toBeInTheDocument()
  })

  it('has no review for a download-only job, since nothing was removed', () => {
    const options = { preset: 'best' as const, format: 'mp4', track: null, keep_music: true }
    render(
      <ul>
        <QueueRow
          job={job({ state: 'done', options, output_name: 'Talk.mp4', link: { url: 'https://youtu.be/jNQXAC9IVRw', site: 'youtu.be', done: 12_000_000, total: 40_000_000 } })}
          actions={{ cancel: vi.fn(), retry: vi.fn(), remove: vi.fn() }}
          onSelect={vi.fn()}
        />
      </ul>,
    )
    expect(screen.queryByRole('button', { name: /Review/ })).toBeNull()
    expect(screen.getByRole('link', { name: 'Download Talk.mp4' })).toBeInTheDocument()
  })
})
