import { megabytes } from '../format'
import type { ModelState, Preset } from '../types'
import styles from './ModelCard.module.css'

interface Props {
  best: ModelState
  fast: ModelState
  onDownload: (preset: Preset, switchJobs: boolean) => void
}

export function ModelCard({ best, fast, onDownload }: Props) {
  const busy = best.downloading ? best : fast.downloading ? fast : null
  const error = best.error ?? fast.error
  return (
    <section className={styles.card} aria-label="Model download">
      <div className={styles.text}>
        <span className="body-strong">The separation model downloads once</span>
        <span className={`small ${styles.detail}`}>
          Best is the Mel-Band RoFormer vocal model, {megabytes(best.size)}. Fast is MDX-Net Voc FT,{' '}
          {megabytes(fast.size)}, quicker and slightly less clean.
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
            {busy.rate > 0 ? ` · ${(busy.rate / 1e6).toFixed(1)} MB/s` : ''}
          </span>
        </div>
      ) : (
        <div className={styles.actions}>
          <button type="button" className="btn-primary" onClick={() => onDownload('best', false)}>
            {error && best.error ? 'Retry' : `Download Best (${megabytes(best.size)})`}
          </button>
          <button type="button" className="btn-quiet" onClick={() => onDownload('fast', true)}>
            Start with Fast ({megabytes(fast.size)})
          </button>
        </div>
      )}
    </section>
  )
}
