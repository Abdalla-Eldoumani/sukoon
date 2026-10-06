import { useState } from 'react'
import { clock, middle } from '../format'
import { ACTIVE, STATE_LABEL } from '../labels'
import type { Job } from '../types'
import { AudioFileIcon, CancelIcon, DeleteIcon, DownloadIcon, RetryIcon, VideoFileIcon } from './icons'
import { JobChoices } from './JobChoices'
import styles from './QueueRow.module.css'

const CANCELABLE = new Set(['checking', 'awaiting_track', 'awaiting_confirm', 'queued', 'waiting_model', 'decoding', 'separating', 'encoding'])
const STOPPED = new Set(['failed', 'canceled', 'interrupted'])

export interface RowActions {
  cancel: (job: Job) => void
  retry: (job: Job) => void
  remove: (job: Job) => void
}

interface Props {
  job: Job
  actions: RowActions
  /** A failed action on this row, shown under the name. */
  problem?: string | null
  /** Rows added after the page loaded slide in; the ones already there do not. */
  arriving?: boolean
  /** A finished row opens its review panel. */
  selected?: boolean
  onSelect?: (job: Job) => void
}

export function QueueRow({ job, actions, problem = null, arriving = false, selected = false, onSelect }: Props) {
  const [confirming, setConfirming] = useState(false)
  const active = ACTIVE.has(job.state)
  const failed = job.state === 'failed'
  const percent = Math.round(job.progress * 100)
  const label = STATE_LABEL[job.state]
  const description = active ? `${label}, ${percent}%` : label
  return (
    <li
      className={[styles.row, arriving && styles.arriving, selected && styles.selected].filter(Boolean).join(' ')}
      aria-label={job.name}
      aria-description={description}
    >
      <span className={styles.glyph}>{job.kind === 'video' ? <VideoFileIcon /> : <AudioFileIcon />}</span>
      <div className={styles.name}>
        {job.state === 'done' && onSelect ? (
          <button
            type="button"
            className={styles.nameButton}
            aria-expanded={selected}
            aria-label={`Review ${job.name}`}
            title={job.name}
            onClick={() => onSelect(job)}
          >
            <bdi className="body-strong" dir="auto">
              {middle(job.name)}
            </bdi>
          </button>
        ) : (
          <bdi className="body-strong" title={job.name} dir="auto">
            {middle(job.name)}
          </bdi>
        )}
        {failed && job.error && <span className={`small ${styles.error}`}>{job.error}</span>}
        {!failed && job.notes.length > 0 && <span className={`small ${styles.note}`}>{job.notes.join(' ')}</span>}
        {problem && <span className={`small ${styles.error}`}>{problem}</span>}
        {confirming && <span className={`small ${styles.note}`}>Delete this job and its cleaned file?</span>}
        <JobChoices job={job} />
      </div>
      <span className={`readout ${styles.duration}`}>{job.duration != null ? clock(job.duration) : ''}</span>
      <div className={styles.stage}>
        <span className={failed ? `label ${styles.faultLabel}` : 'label'}>{label}</span>
        <div className={styles.track} aria-hidden="true">
          <div className={styles.fill} style={{ transform: `scaleX(${job.state === 'done' ? 1 : active ? job.progress : 0})` }} />
        </div>
      </div>
      <span className={`readout ${styles.percent}`}>
        {active && <span>{percent}%</span>}
        {active && job.eta != null && <span title="Time left">{clock(job.eta)}</span>}
      </span>
      <div className={styles.actions}>
        {confirming ? (
          <>
            {/* The icon that opened this is gone, so focus moves to the answer. */}
            <button type="button" className="btn-quiet" autoFocus onClick={() => actions.remove(job)}>
              Delete
            </button>
            <button type="button" className="btn-quiet" onClick={() => setConfirming(false)}>
              Keep
            </button>
          </>
        ) : (
          <>
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
            {STOPPED.has(job.state) && job.retryable && (
              <button type="button" className="btn-quiet btn-icon" aria-label={`Retry ${job.name}`} title="Retry" onClick={() => actions.retry(job)}>
                <RetryIcon />
              </button>
            )}
            {CANCELABLE.has(job.state) && (
              <button type="button" className="btn-quiet btn-icon" aria-label={`Cancel ${job.name}`} title="Cancel" onClick={() => actions.cancel(job)}>
                <CancelIcon />
              </button>
            )}
            {(job.state === 'done' || STOPPED.has(job.state)) && (
              <button
                type="button"
                className="btn-quiet btn-icon"
                aria-label={`Delete ${job.name}`}
                title="Delete"
                onClick={() => (job.state === 'done' ? setConfirming(true) : actions.remove(job))}
              >
                <DeleteIcon />
              </button>
            )}
          </>
        )}
      </div>
    </li>
  )
}
