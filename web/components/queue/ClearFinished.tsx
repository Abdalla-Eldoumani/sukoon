import { useState } from 'react'
import styles from './ClearFinished.module.css'

interface Props {
  /** How many finished jobs the button would clear. */
  count: number
  /** Why the last clear did not go through. */
  error: string | null
  onClear: () => void
}

/** Clears finished jobs and their files, after one question. */
export function ClearFinished({ count, error, onClear }: Props) {
  const [asking, setAsking] = useState(false)
  return (
    <div className={styles.bar}>
      {asking ? (
        <>
          <span className="small">
            Clear {count} finished {count === 1 ? 'job' : 'jobs'} and their files?
          </span>
          <button
            type="button"
            className="btn-quiet btn-small"
            autoFocus
            onClick={() => {
              setAsking(false)
              onClear()
            }}
          >
            Clear
          </button>
          <button type="button" className="btn-quiet btn-small" onClick={() => setAsking(false)}>
            Keep
          </button>
        </>
      ) : (
        <button type="button" className="btn-quiet btn-small" onClick={() => setAsking(true)}>
          Clear finished
        </button>
      )}
      {error && <span className={`small ${styles.error}`}>{error}</span>}
    </div>
  )
}
