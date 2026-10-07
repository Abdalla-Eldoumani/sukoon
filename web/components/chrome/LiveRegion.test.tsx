import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { job } from '../../test/fixtures'
import { LiveRegion } from './LiveRegion'

describe('LiveRegion', () => {
  it('announces state changes and tenths of progress, not every update', () => {
    const { rerender } = render(<LiveRegion jobs={[job({ state: 'queued' })]} />)
    const region = screen.getByRole('status')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toHaveTextContent('')
    rerender(<LiveRegion jobs={[job({ state: 'separating', progress: 0.12 })]} />)
    expect(region).toHaveTextContent('lecture.mp3: Separating, 10%')
    rerender(<LiveRegion jobs={[job({ state: 'separating', progress: 0.18 })]} />)
    expect(region).toHaveTextContent('lecture.mp3: Separating, 10%')
    rerender(<LiveRegion jobs={[job({ state: 'separating', progress: 0.21 })]} />)
    expect(region).toHaveTextContent('lecture.mp3: Separating, 20%')
    rerender(<LiveRegion jobs={[job({ state: 'done', progress: 1 })]} />)
    expect(region).toHaveTextContent('lecture.mp3: Done')
  })
})
