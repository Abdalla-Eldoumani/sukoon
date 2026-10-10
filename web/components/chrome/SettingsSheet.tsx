import { useEffect, useRef, useState } from 'react'
import { request, type Settings } from '../../lib/api/client'
import { megabytes } from '../../lib/text/format'
import { applyTheme, storedTheme, type Theme } from '../../lib/theme/theme'
import { CancelIcon, FolderIcon } from '../ui/icons'
import { Segmented } from '../ui/Segmented'
import styles from './SettingsSheet.module.css'
import { ThemePicker } from './ThemePicker'

interface Props {
  settings: Settings
  /** Why the last change was not saved. */
  error?: string | null
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
export function SettingsSheet({ settings, error = null, library, onChange, onClearFinished, onClose }: Props) {
  const [theme, setTheme] = useState<Theme>(storedTheme)
  const [clearing, setClearing] = useState(false)
  const [openError, setOpenError] = useState<string | null>(null)
  const sheet = useRef<HTMLDialogElement>(null)
  // Kept from the first run only: a second run (StrictMode) would find focus already inside.
  const opener = useRef<HTMLElement | null>(null)

  // A modal dialog keeps focus inside and makes the page behind it inert.
  useEffect(() => {
    const dialog = sheet.current
    opener.current ??= document.activeElement as HTMLElement | null
    if (dialog && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal()
      else dialog.setAttribute('open', '')
    }
    dialog?.querySelector<HTMLElement>('[role=radio][tabindex="0"]')?.focus()
    return () => opener.current?.focus()
  }, [])

  const openFolder = () => {
    setOpenError(null)
    request('/api/library/open', { method: 'POST' }).catch((e: Error) => setOpenError(e.message))
  }

  return (
    <dialog
      ref={sheet}
      className={styles.sheet}
      aria-labelledby="settings-title"
      // Escape reaches onKeyDown first; this only stops the browser closing it a second way.
      onCancel={(e) => e.preventDefault()}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
      }}
      // The contents fill the dialog, so a click that lands on the dialog itself is on the backdrop.
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className={styles.body}>
        <div className={styles.head}>
          <h2 id="settings-title" className="title">
            Settings
          </h2>
          <button type="button" className="btn-quiet btn-icon" aria-label="Close settings" title="Close" onClick={onClose}>
            <CancelIcon />
          </button>
        </div>

        {error && <p className={`small ${styles.error}`}>{error}</p>}
        <section className={styles.group}>
          <h3 className="small">Quality</h3>
          <Segmented
            label="Quality"
            value={settings.preset}
            options={[
              { value: 'best', label: 'Best' },
              { value: 'fast', label: 'Fast' },
            ]}
            onChange={(preset) => onChange({ preset })}
          />
          <p className={`small ${styles.hint}`}>Best gives the cleaner result, and is also faster on a graphics card. Fast always runs on the processor.</p>
        </section>

        <section className={styles.group}>
          <h3 className="small">Device</h3>
          <Segmented
            label="Device"
            value={settings.device}
            options={[
              { value: 'auto', label: 'Auto' },
              { value: 'cpu', label: 'CPU' },
            ]}
            onChange={(device) => onChange({ device })}
          />
          <p className={`small ${styles.hint}`}>
            Auto uses the graphics card when sukoon can use one, and the processor when it can't. Changes apply to files added from now on.
          </p>
        </section>

        <section className={styles.group}>
          <h3 className="small">Default output format</h3>
          <FormatSelect
            label="Audio files"
            value={settings.audio_format}
            formats={settings.formats.audio}
            missing={settings.missing}
            onChange={(audio_format) => onChange({ audio_format })}
          />
          <FormatSelect
            label="Video files"
            value={settings.video_format}
            formats={settings.formats.video}
            missing={settings.missing}
            onChange={(video_format) => onChange({ video_format })}
          />
        </section>

        <section className={styles.group}>
          <h3 className="small">Theme</h3>
          <ThemePicker
            value={theme}
            onChange={(t) => {
              setTheme(t)
              applyTheme(t)
            }}
          />
        </section>

        <section className={styles.group}>
          <h3 className="small">Data folder</h3>
          <p className={`readout ${styles.path}`}>{settings.folder}</p>
          <button type="button" className="btn-quiet" onClick={openFolder}>
            <FolderIcon /> Open the cleaned files
          </button>
          {openError && <p className={`small ${styles.error}`}>{openError}</p>}
        </section>

        <section className={styles.group}>
          <h3 className="small">Storage</h3>
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
    </dialog>
  )
}
