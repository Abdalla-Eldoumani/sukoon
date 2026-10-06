import { megabytes } from '../format'
import type { ModelState, Preset } from '../types'
import styles from './ModelCard.module.css'

interface Props {
  best: ModelState
  fast: ModelState
  onDownload: (preset: Preset, switchJobs: boolean) => void
  /** The server refused to start a download. */
  problem?: string | null
  /** False while another primary action is on screen, so there is only ever one. */
  primary?: boolean
}

export function ModelCard({ best, fast, onDownload, problem = null, primary = true }: Props) {
  const busy = best.downloading ? best : fast.downloading ? fast : null
  const error = problem ?? best.error ?? fast.error
  return (
    <section className={styles.card} aria-label="Model download">
      <div className={styles.text}>
        <h2 className="title">The separation model downloads once</h2>
        <span className={`small ${styles.detail}`}>
          Best, {megabytes(best.size)}, is the cleaner, and the faster one on a graphics card. Fast,{' '}
          {megabytes(fast.size)}, always runs on the processor, for computers without one.
        </span>
        {error && <span className={`small ${styles.error}`}>{error}</span>}
      </div>
      {busy ? (
        <div className={styles.progress}>
          <div className={styles.track} aria-hidden="true">
            <div className={styles.fill} style={{ transform: `scaleX(${busy.size ? busy.done / busy.size : 0})` }} />
          </div>
          <span className="readout" role="status">
            {megabytes(busy.done)} of {megabytes(busy.size)}
            {busy.rate > 0 ? ` at ${(busy.rate / 1e6).toFixed(1)} MB/s` : ''}
          </span>
        </div>
      ) : (
        <div className={styles.actions}>
          <button
            type="button"
            className={primary ? 'btn-primary' : 'btn-quiet'}
            onClick={() => (fast.error && !best.error ? onDownload('fast', true) : onDownload('best', false))}
          >
            {error ? 'Retry' : `Download Best (${megabytes(best.size)})`}
          </button>
          <button type="button" className="btn-quiet" onClick={() => onDownload('fast', true)}>
            Start with Fast ({megabytes(fast.size)})
          </button>
        </div>
      )}
    </section>
  )
}
