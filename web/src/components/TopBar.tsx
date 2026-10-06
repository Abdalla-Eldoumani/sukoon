import { megabytes } from '../format'
import { SettingsIcon } from './icons'
import styles from './TopBar.module.css'

interface Props {
  device: string | null
  /** Bytes held by jobs, which Clear finished frees. */
  library: number | null
  /** Null until the settings have loaded, which leaves the button disabled. */
  onSettings: (() => void) | null
}

export function TopBar({ device, library, onSettings }: Props) {
  return (
    <header className={styles.bar}>
      <div className={styles.inner}>
        <h1 className={styles.wordmark}>sukoon</h1>
        <div className={styles.status}>
          {device && (
            <span className="readout" title="Device used for separation">
              {device}
            </span>
          )}
          {library != null && (
            <span className="readout" title="Space used by jobs">
              {megabytes(library)}
            </span>
          )}
          <button
            type="button"
            className="btn-quiet btn-icon"
            aria-label="Settings"
            title="Settings"
            onClick={onSettings ?? undefined}
            disabled={!onSettings}
          >
            <SettingsIcon />
          </button>
        </div>
      </div>
    </header>
  )
}
