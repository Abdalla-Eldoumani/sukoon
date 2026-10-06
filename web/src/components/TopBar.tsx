import { SettingsIcon } from './icons'
import styles from './TopBar.module.css'

interface Props {
  device: string | null
}

export function TopBar({ device }: Props) {
  return (
    <header className={styles.bar}>
      <div className={styles.inner}>
        <span className={styles.wordmark}>sukoon</span>
        <div className={styles.status}>
          {device && (
            <span className="readout" title="Device used for separation">
              {device}
            </span>
          )}
          <button
            type="button"
            className="btn-quiet btn-icon"
            aria-label="Settings"
            title="Settings"
            disabled
          >
            <SettingsIcon />
          </button>
        </div>
      </div>
    </header>
  )
}
