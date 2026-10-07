import { useState } from 'react'
import { clock, megabytes } from '../../lib/text/format'
import { ACTIVE, STATE_LABEL } from '../../lib/text/labels'
import type { Job } from '../../lib/api/types'
import { AudioFileIcon, CancelIcon, DeleteIcon, DownloadIcon, LinkIcon, RetryIcon, VideoFileIcon } from '../ui/icons'
import { hasChoices, JobChoices } from './JobChoices'
import { Lane, position } from './Lane'
import styles from './QueueRow.module.css'

const CANCELABLE = new Set(['fetching', 'checking', 'awaiting_track', 'awaiting_confirm', 'queued', 'waiting_model', 'decoding', 'separating', 'encoding'])
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

/** What sits after the stage word: where a link came from, what it was checked as, and the format. */
function details(job: Job): string[] {
  const out: string[] = []
  if (job.link) {
    out.push(`from ${job.link.site}`)
    // Only once ffprobe has read it, the same check an upload gets; never a virus scan.
    if (job.kind) out.push(`checked as real ${job.kind}`)
    if (job.options.keep_music) out.push('download only')
  }
  if (job.state === 'done' && job.output_name) out.push(job.output_name.split('.').pop()!.toUpperCase())
  return out
}

function Time({ job }: { job: Job }) {
  let main = job.duration != null ? clock(job.duration) : ''
  let sub: string | null = null
  if (job.state === 'fetching' && job.link && job.link.done > 0) {
    main = job.link.total ? `${megabytes(job.link.done)} of ${megabytes(job.link.total)}` : `${megabytes(job.link.done)} so far`
  } else if (job.state === 'uploading') {
    main = `${Math.round(job.progress * 100)}%`
  } else if (job.through !== null) {
    main = job.duration ? `${clock(job.through * job.duration)} of ${clock(job.duration)}` : `${Math.round(job.through * 100)}%`
  }
  if (ACTIVE.has(job.state) && job.eta != null) sub = `${clock(job.eta)} left`
  return (
    <div className={styles.time}>
      <span className="readout-strong">{main}</span>
      {sub && <span className={`readout ${styles.left}`}>{sub}</span>}
    </div>
  )
}

export function QueueRow({ job, actions, problem = null, arriving = false, selected = false, onSelect }: Props) {
  const [confirming, setConfirming] = useState(false)
  const failed = job.state === 'failed'
  const label = STATE_LABEL[job.state]
  const description = ACTIVE.has(job.state) ? `${label}, ${Math.round(job.progress * 100)}%` : label
  // Download only has nothing to compare, so it has no review panel.
  const reviewable = job.state === 'done' && !job.options.keep_music
  // A stage word fades in when it changes, never on first paint; a strip draws in only when its
  // job finishes while the page is open.
  const [firstLabel] = useState(label)
  const [sawWork] = useState(job.state !== 'done')
  // Choices and reasons need room, and a lane with nothing to draw can give it.
  const wide = (failed || !!problem || hasChoices(job)) && position(job) === null && job.state !== 'done'
  const name = (
    <span className={`name ${styles.nameText}`} dir="auto">
      {job.name}
    </span>
  )
  return (
    <li
      className={[styles.row, wide && styles.wide, arriving && styles.arriving, selected && styles.selected]
        .filter(Boolean)
        .join(' ')}
      aria-label={job.name}
      aria-description={description}
    >
      <span className={styles.glyph}>
        {job.kind === 'video' ? <VideoFileIcon /> : job.link && !job.kind ? <LinkIcon /> : <AudioFileIcon />}
      </span>
      <div className={styles.name}>
        {reviewable && onSelect ? (
          <button
            type="button"
            className={styles.nameButton}
            aria-expanded={selected}
            aria-label={`Review ${job.name}`}
            title={job.name}
            onClick={() => onSelect(job)}
          >
            {name}
          </button>
        ) : (
          <span className={styles.nameBlock} title={job.name}>
            {name}
          </span>
        )}
        <p className={`small ${styles.line}`}>
          <span
            key={label}
            className={[styles.stage, failed && styles.fault, label !== firstLabel && styles.changed]
              .filter(Boolean)
              .join(' ')}
          >
            {label}
          </span>
          {details(job).map((d) => `, ${d}`)}
        </p>
        {failed && job.error && <p className={`small ${styles.error}`}>{job.error}</p>}
        {!failed && job.notes.length > 0 && <p className={`small ${styles.note}`}>{job.notes.join(' ')}</p>}
        {problem && <p className={`small ${styles.error}`}>{problem}</p>}
        {confirming && (
          <div className={styles.confirm}>
            <span className="small">Delete this job and its cleaned file?</span>
            {/* The icon that opened this is gone, so focus moves to the answer. */}
            <button type="button" className="btn-quiet btn-small" autoFocus onClick={() => actions.remove(job)}>
              Delete
            </button>
            <button type="button" className="btn-quiet btn-small" onClick={() => setConfirming(false)}>
              Keep
            </button>
          </div>
        )}
        <JobChoices job={job} />
      </div>
      <Lane job={job} drawIn={sawWork} className={styles.lane} />
      <Time job={job} />
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
        {(job.state === 'done' || STOPPED.has(job.state)) && !confirming && (
          <button
            type="button"
            className="btn-quiet btn-icon"
            aria-label={`Delete ${job.name}`}
            title="Delete"
            onClick={(e) => {
              // A queued job stops at once, so this lands under the second click of a double click on Cancel.
              if (e.detail > 1) return
              if (job.state === 'done') setConfirming(true)
              else actions.remove(job)
            }}
          >
            <DeleteIcon />
          </button>
        )}
      </div>
    </li>
  )
}
