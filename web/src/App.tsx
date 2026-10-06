import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { getJson, postJson, request, type Health } from './api'
import styles from './App.module.css'
import { DropWell } from './components/DropWell'
import { LiveRegion } from './components/LiveRegion'
import { ReviewPanel } from './components/ReviewPanel'
import { ModelCard } from './components/ModelCard'
import { QueueRow, type RowActions } from './components/QueueRow'
import { TopBar } from './components/TopBar'
import { useServerState } from './serverState'
import type { Job, Preset } from './types'
import { uploadFile } from './upload'
import { useWindowDrag } from './useWindowDrag'

function localJob(id: string, file: File): Job {
  return {
    id,
    created: Date.now() / 1000,
    name: file.name,
    kind: file.type.startsWith('video/') ? 'video' : 'audio',
    state: 'uploading',
    progress: 0,
    eta: null,
    error: null,
    retryable: false,
    options: { preset: 'best', format: null, track: null },
    duration: null,
    tracks: [],
    notes: [],
    formats: [],
    offset: 0,
    confirm: null,
    output_name: null,
  }
}

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const server = useServerState()
  const [uploads, setUploads] = useState<Job[]>([])
  const queue = useRef(Promise.resolve())
  const counter = useRef(0)
  const [problems, setProblems] = useState<Record<string, string>>({})
  const [library, setLibrary] = useState<number | null>(null)
  const [clearing, setClearing] = useState(false)
  const [reviewing, setReviewing] = useState<string | null>(null)

  // One upload at a time keeps jobs in the order the files were dropped.
  const addFiles = useCallback((files: File[]) => {
    for (const file of files) {
      const id = `local-${(counter.current += 1)}`
      setUploads((u) => [...u, localJob(id, file)])
      const patch = (fields: Partial<Job>) => setUploads((u) => u.map((j) => (j.id === id ? { ...j, ...fields } : j)))
      queue.current = queue.current.then(() =>
        uploadFile(file, (progress) => patch({ progress })).then(
          () => setUploads((u) => u.filter((j) => j.id !== id)),
          (err: Error) => patch({ state: 'failed', error: err.message, progress: 0 }),
        ),
      )
    }
  }, [])
  const dragging = useWindowDrag(addFiles)

  useEffect(() => {
    getJson<Health>('/api/health').then(setHealth, () => setHealth(null))
  }, [])

  // The library only changes size when a job finishes or goes away.
  const settled = server.jobs
    .filter((j) => ['done', 'failed', 'canceled', 'interrupted'].includes(j.state))
    .map((j) => j.id)
    .join()
  useEffect(() => {
    if (!server.connected) return
    getJson<{ jobs: number }>('/api/library').then((l) => setLibrary(l.jobs), () => setLibrary(null))
  }, [server.connected, settled, server.jobs.length])

  const attempt = (job: Job, request: Promise<unknown>) => {
    setProblems((p) => {
      const next = { ...p }
      delete next[job.id]
      return next
    })
    request.catch((e: Error) => setProblems((p) => ({ ...p, [job.id]: e.message })))
  }
  const actions: RowActions = {
    cancel: (job) => attempt(job, postJson(`/api/jobs/${job.id}/cancel`)),
    retry: (job) => attempt(job, postJson(`/api/jobs/${job.id}/retry`)),
    remove: (job) => {
      if (job.id.startsWith('local-')) setUploads((u) => u.filter((j) => j.id !== job.id))
      else attempt(job, request(`/api/jobs/${job.id}`, { method: 'DELETE' }))
    },
  }
  // Opening and closing the panel cross-fades where the browser has view transitions.
  const select = (job: Job) => {
    const change = () => setReviewing((id) => (id === job.id ? null : job.id))
    const quiet = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (document.startViewTransition && !quiet) document.startViewTransition(() => flushSync(change))
    else change()
  }
  const finished = server.jobs.filter((j) => ['done', 'failed', 'canceled', 'interrupted'].includes(j.state))
  const clearFinished = () => {
    setClearing(false)
    void postJson('/api/library/clear')
  }

  const download = (preset: Preset, switchJobs: boolean) => {
    void fetch(`/api/models/${preset}/download${switchJobs ? '?switch=1' : ''}`, { method: 'POST' })
  }

  const uploadingNames = new Set(uploads.filter((u) => u.state === 'uploading').map((u) => u.name))
  const rows = [...server.jobs.filter((j) => !(j.state === 'checking' && uploadingNames.has(j.name))), ...uploads]
  const best = server.models.find((m) => m.preset === 'best')
  const fast = server.models.find((m) => m.preset === 'fast')
  const needsModel =
    server.jobs.some((j) => j.state === 'waiting_model') || server.models.some((m) => m.downloading || m.error)

  return (
    <>
      <TopBar device={health?.device ?? null} library={library} />
      <main className={styles.main}>
        <DropWell compact={rows.length > 0} dragging={dragging} onFiles={addFiles} />
        {rows.length === 0 && (
          <p className={styles.note}>
            Voices stay. Instruments, and most other non-voice sounds, are removed. Everything happens on this
            computer.
          </p>
        )}
        {needsModel && best && fast && <ModelCard best={best} fast={fast} onDownload={download} />}
        {finished.length > 0 && (
          <div className={styles.queueBar}>
            {clearing ? (
              <>
                <span className="small">
                  Clear {finished.length} finished {finished.length === 1 ? 'job' : 'jobs'} and their files?
                </span>
                <button type="button" className="btn-quiet" onClick={clearFinished}>
                  Clear
                </button>
                <button type="button" className="btn-quiet" onClick={() => setClearing(false)}>
                  Keep
                </button>
              </>
            ) : (
              <button type="button" className="btn-quiet" onClick={() => setClearing(true)}>
                Clear finished
              </button>
            )}
          </div>
        )}
        {rows.length > 0 && (
          <ol className={styles.queue} aria-label="Queue">
            {rows.map((job) => (
              <Fragment key={job.id}>
                <QueueRow
                  job={job}
                  actions={actions}
                  problem={problems[job.id] ?? null}
                  arriving={server.initial !== null && !server.initial.has(job.id)}
                  selected={reviewing === job.id}
                  onSelect={select}
                />
                {reviewing === job.id && job.state === 'done' && (
                  <li className={styles.panelItem}>
                    <ReviewPanel job={job} />
                  </li>
                )}
              </Fragment>
            ))}
          </ol>
        )}
      </main>
      <LiveRegion jobs={rows} />
      {dragging && <div className={styles.frame} aria-hidden="true" data-testid="drag-frame" />}
    </>
  )
}
