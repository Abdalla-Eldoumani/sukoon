import { useState } from 'react'
import { postJson } from '../api'
import type { Job, Track } from '../types'
import styles from './JobChoices.module.css'

const CHOOSABLE = new Set(['awaiting_track', 'awaiting_confirm', 'queued', 'waiting_model'])
// A link can switch to download only until it starts running, even while it is fetched.
const EARLY = new Set(['fetching', 'checking', ...CHOOSABLE])

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

export function hasChoices(job: Job): boolean {
  return CHOOSABLE.has(job.state) || (job.link !== null && EARLY.has(job.state))
}

/** The choices a job takes before it runs: which audio track, which format, and re-encode consent. */
export function JobChoices({ job }: Props) {
  const defaultTrack = job.options.track ?? Math.max(0, job.tracks.findIndex((t) => t.default))
  const [track, setTrack] = useState(defaultTrack)
  const [error, setError] = useState<string | null>(null)
  const early = job.link !== null && EARLY.has(job.state)
  if (!hasChoices(job)) return null

  const send = (body: Record<string, unknown>) => {
    setError(null)
    postJson(`/api/jobs/${job.id}/choose`, body).catch((e: Error) => setError(e.message))
  }
  const fromVideo = job.kind === 'video'
  return (
    <div className={styles.choices}>
      {job.state === 'awaiting_confirm' && job.confirm && <span className={`small ${styles.text}`}>{job.confirm}</span>}
      <div className={styles.controls}>
        {early && (
          <label className={`small ${styles.toggle}`}>
            <input
              type="checkbox"
              role="switch"
              aria-label={`Remove music from ${job.name}`}
              checked={!job.options.keep_music}
              onChange={(e) => send({ keep_music: !e.target.checked })}
            />
            Remove music
          </label>
        )}
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
              <option
                key={f.value}
                value={f.value}
                disabled={f.missing !== null}
                title={f.missing ? `Needs the ${f.missing} encoder` : undefined}
              >
                {formatLabel(f.value, f.video, f.reencode, fromVideo)}
                {f.missing ? ` (needs ${f.missing})` : ''}
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
