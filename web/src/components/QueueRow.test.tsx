import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { job } from '../test/fixtures'
import { QueueRow } from './QueueRow'

function row(fields: Parameters<typeof job>[0]) {
  return render(
    <ul>
      <QueueRow job={job(fields)} />
    </ul>,
  )
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
})
