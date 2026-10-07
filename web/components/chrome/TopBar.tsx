import { megabytes } from '../../lib/text/format'
import { SettingsIcon } from '../ui/icons'
import styles from './TopBar.module.css'

interface Props {
  device: string | null
  /** Bytes held by jobs, which Clear finished frees. */
  library: number | null
  /** Null until the settings have loaded, which leaves the button disabled; the setup screen has none. */
  onSettings?: (() => void) | null
}

export function TopBar({ device, library, onSettings }: Props) {
  // The server says "CUDA · GeForce RTX 3060 Laptop" or "CPU": the kind becomes the label.
  const [kind, name] = device?.includes(' · ') ? device.split(' · ', 2) : ['Device', device]
  return (
    <header className={styles.bar}>
      <div className={styles.inner}>
        <h1 className={styles.wordmark}>
          sukoon{' '}
          <span className={styles.arabic} lang="ar" dir="rtl">
            سكون
          </span>
        </h1>
        <div className={styles.status}>
          {name && (
            <span className={styles.item} title="Device used for separation">
              <span className={`small ${styles.key}`}>{kind}</span> <span className="readout">{name}</span>
            </span>
          )}
          {library != null && (
            <span className={`${styles.item} ${styles.library}`} title="Space used by jobs">
              <span className={`small ${styles.key}`}>Library</span> <span className="readout">{megabytes(library)}</span>
            </span>
          )}
          {onSettings !== undefined && (
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
          )}
        </div>
      </div>
    </header>
  )
}
