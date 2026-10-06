import { useState } from 'react'
import { postJson } from '../api'
import type { Job, Track } from '../types'
import styles from './JobChoices.module.css'

const CHOOSABLE = new Set(['awaiting_track', 'awaiting_confirm', 'queued', 'waiting_model'])

function trackLabel(track: Track, index: number): string {
  const layout = track.channels === 1 ? 'mono' : track.channels === 2 ? 'stereo' : track.channels ? `${track.channels} channels` : null
  return [`Track ${index + 1}`, track.language, track.title, layout].filter(Boolean).join(' · ')
}

function formatLabel(value: string, video: boolean, reencode: boolean, fromVideo: boolean): string {
  if (reencode) return `${value.toUpperCase()} (re-encodes the picture)`
  if (fromVideo && !video) return `${value.toUpperCase()} (audio only)`
  return value.toUpperCase()
}

interface Props {
  job: Job
}

/** The choices a job takes before it runs: which audio track, which format, and re-encode consent. */
export function JobChoices({ job }: Props) {
  const defaultTrack = job.options.track ?? 0
  const [track, setTrack] = useState(defaultTrack)
  const [error, setError] = useState<string | null>(null)
  if (!CHOOSABLE.has(job.state)) return null

  const send = (body: Record<string, unknown>) => {
    setError(null)
    postJson(`/api/jobs/${job.id}/choose`, body).catch((e: Error) => setError(e.message))
  }
  const fromVideo = job.kind === 'video'
  return (
    <div className={styles.choices}>
      {job.state === 'awaiting_confirm' && job.confirm && <span className={`small ${styles.text}`}>{job.confirm}</span>}
      <div className={styles.controls}>
        {job.state === 'awaiting_track' && (
          <>
            <select className="select" aria-label={`Audio track for ${job.name}`} value={track} onChange={(e) => setTrack(Number(e.target.value))}>
              {job.tracks.map((t, i) => (
                <option key={i} value={i}>
                  {trackLabel(t, i)}
                </option>
              ))}
            </select>
            <button type="button" className="btn-quiet" onClick={() => send({ track })}>
              Continue
            </button>
          </>
        )}
        {job.formats.length > 0 && (
          <select
            className="select"
            aria-label={`Output format for ${job.name}`}
            value={job.options.format ?? ''}
            onChange={(e) => send({ format: e.target.value })}
          >
            {job.formats.map((f) => (
              <option key={f.value} value={f.value}>
                {formatLabel(f.value, f.video, f.reencode, fromVideo)}
              </option>
            ))}
          </select>
        )}
        {job.state === 'awaiting_confirm' && (
          <button type="button" className="btn-quiet" onClick={() => send({ confirm: true })}>
            Re-encode
          </button>
        )}
      </div>
      {error && <span className={`small ${styles.error}`}>{error}</span>}
    </div>
  )
}
