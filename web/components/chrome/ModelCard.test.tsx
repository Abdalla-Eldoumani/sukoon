import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { model } from '../../test/fixtures'
import { ModelCard } from './ModelCard'

const fast = model({ preset: 'fast', size: 66_762_490 })

describe('ModelCard', () => {
  it('offers both choices with their sizes', async () => {
    const onDownload = vi.fn()
    render(<ModelCard best={model()} fast={fast} onDownload={onDownload} />)
    await userEvent.click(screen.getByRole('button', { name: 'Download Best (913 MB)' }))
    expect(onDownload).toHaveBeenLastCalledWith('best', false)
    await userEvent.click(screen.getByRole('button', { name: 'Start with Fast (67 MB)' }))
    expect(onDownload).toHaveBeenLastCalledWith('fast', true)
  })

  it('shows bytes and speed while downloading', () => {
    render(<ModelCard best={model({ downloading: true, done: 456_000_000, rate: 12_300_000 })} fast={fast} onDownload={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent('456 MB of 913 MB at 12.3 MB/s')
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('says what went wrong and offers a retry', () => {
    const error = "Couldn't download the model. Check your connection, then retry."
    render(<ModelCard best={model({ error })} fast={fast} onDownload={() => {}} />)
    expect(screen.getByText(error)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
