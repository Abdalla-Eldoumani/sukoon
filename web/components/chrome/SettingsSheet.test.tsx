import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Settings } from '../../lib/api/client'
import { SettingsSheet } from './SettingsSheet'

const settings: Settings = {
  preset: 'best',
  device: 'auto',
  audio_format: null,
  video_format: null,
  missing: { opus: 'libopus' },
  folder: '/home/me/.local/share/sukoon',
}

afterEach(() => {
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

function open(onChange = vi.fn(), onClose = vi.fn()) {
  render(
    <SettingsSheet settings={settings} library={{ jobs: 312e6, models: 980e6 }} onChange={onChange} onClearFinished={() => {}} onClose={onClose} />,
  )
  return { onChange, onClose }
}

describe('SettingsSheet', () => {
  it('is a dialog that starts on the quality choice', () => {
    open()
    expect(screen.getByRole('dialog', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Best' })).toHaveFocus()
  })

  it('changes quality with a click and device with the arrow keys', async () => {
    const { onChange } = open()
    await userEvent.click(screen.getByRole('radio', { name: 'Fast' }))
    expect(onChange).toHaveBeenLastCalledWith({ preset: 'fast' })
    screen.getByRole('radio', { name: 'Auto' }).focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith({ device: 'cpu' })
  })

  it('sets default formats and disables the ones ffmpeg cannot write', async () => {
    const { onChange } = open()
    const audio = screen.getByRole('combobox', { name: 'Audio files' })
    expect(screen.getByRole('option', { name: 'OPUS (needs libopus)' })).toBeDisabled()
    await userEvent.selectOptions(audio, 'FLAC')
    expect(onChange).toHaveBeenLastCalledWith({ audio_format: 'flac' })
    await userEvent.selectOptions(audio, 'Same as the file')
    expect(onChange).toHaveBeenLastCalledWith({ audio_format: null })
  })

  it('keeps the theme in the browser only', async () => {
    const { onChange } = open()
    await userEvent.click(screen.getByRole('radio', { name: 'Light' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(window.localStorage.getItem('sukoon.theme')).toBe('light')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('stays open when a click lands in the space between its sections', async () => {
    const { onClose } = open()
    await userEvent.click(screen.getByRole('heading', { name: 'Settings' }).parentElement!.parentElement!)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows the data folder and storage, and closes on Escape', async () => {
    const { onClose } = open()
    expect(screen.getByText('/home/me/.local/share/sukoon')).toBeInTheDocument()
    expect(screen.getByText('312 MB')).toBeInTheDocument()
    expect(screen.getByText('980 MB')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
