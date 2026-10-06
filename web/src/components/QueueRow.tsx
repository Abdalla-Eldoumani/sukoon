import { clock, middle } from '../format'
import { ACTIVE, STATE_LABEL } from '../labels'
import type { Job } from '../types'
import { AudioFileIcon, DownloadIcon, VideoFileIcon } from './icons'
import styles from './QueueRow.module.css'

interface Props {
  job: Job
  /** Rows added after the page loaded slide in; the ones already there do not. */
  arriving?: boolean
}

export function QueueRow({ job, arriving = false }: Props) {
  const active = ACTIVE.has(job.state)
  const failed = job.state === 'failed'
  const percent = Math.round(job.progress * 100)
  const label = STATE_LABEL[job.state]
  const description = active ? `${label}, ${percent}%` : label
  return (
    <li className={arriving ? `${styles.row} ${styles.arriving}` : styles.row} aria-label={job.name} aria-description={description}>
      <span className={styles.glyph}>{job.kind === 'video' ? <VideoFileIcon /> : <AudioFileIcon />}</span>
      <div className={styles.name}>
        <bdi className="body-strong" title={job.name} dir="auto">
          {middle(job.name)}
        </bdi>
        {failed && job.error && <span className={`small ${styles.error}`}>{job.error}</span>}
        {!failed && job.notes.length > 0 && <span className={`small ${styles.note}`}>{job.notes.join(' ')}</span>}
      </div>
      <span className={`readout ${styles.duration}`}>{job.duration != null ? clock(job.duration) : ''}</span>
      <div className={styles.stage}>
        <span className={failed ? `label ${styles.faultLabel}` : 'label'}>{label}</span>
        <div className={styles.track} aria-hidden="true">
          <div
            className={styles.fill}
            style={{ transform: `scaleX(${job.state === 'done' ? 1 : active ? job.progress : 0})` }}
          />
        </div>
      </div>
      <span className={`readout ${styles.percent}`}>{active ? `${percent}%` : ''}</span>
      <div className={styles.actions}>
        {job.state === 'done' && job.output_name && (
          <a
            className="btn-quiet btn-icon"
            href={`/api/jobs/${job.id}/output`}
            download={job.output_name}
            aria-label={`Download ${job.output_name}`}
            title="Download"
          >
            <DownloadIcon />
          </a>
        )}
      </div>
    </li>
  )
}
