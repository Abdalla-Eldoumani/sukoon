import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Segmented } from './Segmented'

const OPTIONS = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
  { value: 'c', label: 'Gamma' },
]

function Chosen({ onChange }: { onChange: (value: string) => void }) {
  const [value, setValue] = useState('a')
  return (
    <Segmented
      label="Greek"
      value={value}
      options={OPTIONS}
      onChange={(v) => {
        setValue(v)
        onChange(v)
      }}
    />
  )
}

describe('Segmented', () => {
  it('checks the chosen option and leaves only it in the tab order', () => {
    render(<Segmented label="Greek" value="b" options={OPTIONS} onChange={() => undefined} />)
    expect(screen.getByRole('radiogroup', { name: 'Greek' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Beta' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'Beta' })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('radio', { name: 'Alpha' })).toHaveAttribute('tabindex', '-1')
  })

  it('moves the choice and the focus with the arrow keys, wrapping at the ends', async () => {
    const onChange = vi.fn()
    render(<Chosen onChange={onChange} />)
    screen.getByRole('radio', { name: 'Alpha' }).focus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(onChange).toHaveBeenLastCalledWith('c')
    expect(screen.getByRole('radio', { name: 'Gamma' })).toHaveFocus()
    await userEvent.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith('a')
    expect(screen.getByRole('radio', { name: 'Alpha' })).toHaveFocus()
  })

  it('ignores keys that are not arrows', async () => {
    const onChange = vi.fn()
    render(<Segmented label="Greek" value="a" options={OPTIONS} onChange={onChange} />)
    screen.getByRole('radio', { name: 'Alpha' }).focus()
    await userEvent.keyboard('x')
    expect(onChange).not.toHaveBeenCalled()
  })
})
