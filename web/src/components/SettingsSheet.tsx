import { useEffect, useRef, useState } from 'react'
import { postJson, type Settings } from '../api'
import { megabytes } from '../format'
import { applyTheme, storedTheme, type Theme } from '../theme'
import { CancelIcon, FolderIcon } from './icons'
import { Segmented } from './Segmented'
import styles from './SettingsSheet.module.css'

const AUDIO = ['mp3', 'm4a', 'wav', 'flac', 'opus', 'ogg']
const VIDEO = ['mp4', 'mkv', 'webm', 'mov']

interface Props {
  settings: Settings
  library: { jobs: number; models: number } | null
  onChange: (values: Partial<Settings>) => void
  onClearFinished: () => void
  onClose: () => void
}

function FormatSelect({ label, value, formats, missing, onChange }: {
  label: string
  value: string | null
  formats: string[]
  missing: Record<string, string>
  onChange: (value: string | null) => void
}) {
  return (
    <label className={styles.formatRow}>
      <span className="small">{label}</span>
      <select className="select" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Same as the file</option>
        {formats.map((f) => (
          <option key={f} value={f} disabled={f in missing} title={f in missing ? `Needs the ${missing[f]} encoder` : undefined}>
            {f.toUpperCase()}
            {f in missing ? ` (needs ${missing[f]})` : ''}
          </option>
        ))}
      </select>
    </label>
  )
}

/** Quality, device, default formats, theme, and where files live. Escape or the close button shuts it. */
export function SettingsSheet({ settings, library, onChange, onClearFinished, onClose }: Props) {
  const [theme, setTheme] = useState<Theme>(storedTheme)
  const [clearing, setClearing] = useState(false)
  const sheet = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    sheet.current?.querySelector<HTMLElement>('[role=radio][tabindex="0"]')?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      opener?.focus()
    }
  }, [onClose])

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <div ref={sheet} className={styles.sheet} role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div className={styles.head}>
          <h2 id="settings-title" className="title">
            Settings
          </h2>
          <button type="button" className="btn-quiet btn-icon" aria-label="Close settings" title="Close" onClick={onClose}>
            <CancelIcon />
          </button>
        </div>

        <section className={styles.group}>
          <h3 className="label">Quality</h3>
          <Segmented
            label="Quality"
            value={settings.preset}
            options={[
              { value: 'best', label: 'Best' },
              { value: 'fast', label: 'Fast' },
            ]}
            onChange={(preset) => onChange({ preset })}
          />
          <p className={`small ${styles.hint}`}>Best is cleaner and slower. Fast suits long lectures on a CPU.</p>
        </section>

        <section className={styles.group}>
          <h3 className="label">Device</h3>
          <Segmented
            label="Device"
            value={settings.device}
            options={[
              { value: 'auto', label: 'Auto' },
              { value: 'cpu', label: 'CPU' },
            ]}
            onChange={(device) => onChange({ device })}
          />
          <p className={`small ${styles.hint}`}>Auto uses the graphics card when torch can reach it.</p>
        </section>

        <section className={styles.group}>
          <h3 className="label">Default output format</h3>
          <FormatSelect
            label="Audio files"
            value={settings.audio_format}
            formats={AUDIO}
            missing={settings.missing}
            onChange={(audio_format) => onChange({ audio_format })}
          />
          <FormatSelect
            label="Video files"
            value={settings.video_format}
            formats={VIDEO}
            missing={settings.missing}
            onChange={(video_format) => onChange({ video_format })}
          />
        </section>

        <section className={styles.group}>
          <h3 className="label">Theme</h3>
          <Segmented
            label="Theme"
            value={theme}
            options={[
              { value: 'system', label: 'System' },
              { value: 'dark', label: 'Dark' },
              { value: 'light', label: 'Light' },
            ]}
            onChange={(t) => {
              setTheme(t)
              applyTheme(t)
            }}
          />
        </section>

        <section className={styles.group}>
          <h3 className="label">Data folder</h3>
          <p className={`readout ${styles.path}`}>{settings.folder}</p>
          <button type="button" className="btn-quiet" onClick={() => void postJson('/api/library/open')}>
            <FolderIcon /> Open folder
          </button>
        </section>

        <section className={styles.group}>
          <h3 className="label">Storage</h3>
          {library && (
            <p className="small">
              <span className="readout">{megabytes(library.jobs)}</span> in jobs,{' '}
              <span className="readout">{megabytes(library.models)}</span> in models
            </p>
          )}
          {clearing ? (
            <div className={styles.confirm}>
              <span className="small">Delete every finished job and its files?</span>
              <button
                type="button"
                className="btn-quiet"
                autoFocus
                onClick={() => {
                  setClearing(false)
                  onClearFinished()
                }}
              >
                Clear
              </button>
              <button type="button" className="btn-quiet" onClick={() => setClearing(false)}>
                Keep
              </button>
            </div>
          ) : (
            <button type="button" className="btn-quiet" onClick={() => setClearing(true)}>
              Clear finished jobs
            </button>
          )}
        </section>
      </div>
    </>
  )
}
