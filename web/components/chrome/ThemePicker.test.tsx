import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ThemePicker } from './ThemePicker'

describe('ThemePicker', () => {
  it('offers every theme, with the chosen one checked and focusable', () => {
    render(<ThemePicker value="midnight" onChange={() => undefined} />)
    const radios = screen.getAllByRole('radio')
    expect(radios.map((r) => r.textContent)).toEqual(['System', 'Night', 'Day', 'High contrast', 'Parchment', 'Midnight'])
    const chosen = screen.getByRole('radio', { name: 'Midnight' })
    expect(chosen).toHaveAttribute('aria-checked', 'true')
    expect(chosen).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('radio', { name: 'Night' })).toHaveAttribute('tabindex', '-1')
  })

  it('moves the choice with the arrow keys, wrapping at the ends', async () => {
    const onChange = vi.fn()
    render(<ThemePicker value="system" onChange={onChange} />)
    screen.getByRole('radio', { name: 'System' }).focus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(onChange).toHaveBeenLastCalledWith('midnight')
    await userEvent.keyboard('{ArrowDown}')
    expect(onChange).toHaveBeenLastCalledWith('dark')
  })

  it('draws each swatch in its own theme', () => {
    const { container } = render(<ThemePicker value="system" onChange={() => undefined} />)
    const palettes = [...container.querySelectorAll('[data-theme]')].map((e) => e.getAttribute('data-theme'))
    expect(palettes).toEqual(['dark', 'light', 'dark', 'light', 'contrast', 'parchment', 'midnight'])
  })
})
