import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Settings } from '../../lib/api/client'
import { SettingsSheet } from './SettingsSheet'

const settings: Settings = {
  preset: 'best',
  device: 'auto',
  audio_format: null,
  video_format: null,
  formats: { audio: ['mp3', 'm4a', 'wav', 'flac', 'opus', 'ogg'], video: ['mp4', 'mkv', 'webm', 'mov'] },
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

  it('lists the formats the server sends, in its order', () => {
    render(
      <SettingsSheet
        settings={{ ...settings, formats: { audio: ['wav', 'mp3'], video: ['mkv'] }, missing: {} }}
        library={null}
        onChange={() => {}}
        onClearFinished={() => {}}
        onClose={() => {}}
      />,
    )
    const names = (label: string) => within(screen.getByRole('combobox', { name: label })).getAllByRole('option').map((o) => o.textContent)
    expect(names('Audio files')).toEqual(['Same as the file', 'WAV', 'MP3'])
    expect(names('Video files')).toEqual(['Same as the file', 'MKV'])
  })

  it('keeps the theme in the browser only', async () => {
    const { onChange } = open()
    await userEvent.click(screen.getByRole('radio', { name: 'Parchment' }))
    expect(document.documentElement.dataset.theme).toBe('parchment')
    expect(window.localStorage.getItem('sukoon.theme')).toBe('parchment')
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
