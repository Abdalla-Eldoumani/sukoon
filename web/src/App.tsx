import { useCallback, useEffect, useRef, useState } from 'react'
import { getJson, type Health } from './api'
import styles from './App.module.css'
import { DropWell } from './components/DropWell'
import { ModelCard } from './components/ModelCard'
import { QueueRow } from './components/QueueRow'
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
      <TopBar device={health?.device ?? null} />
      <main className={styles.main}>
        <DropWell compact={rows.length > 0} dragging={dragging} onFiles={addFiles} />
        {rows.length === 0 && (
          <p className={styles.note}>
            Voices stay. Instruments, and most other non-voice sounds, are removed. Everything happens on this
            computer.
          </p>
        )}
        {needsModel && best && fast && <ModelCard best={best} fast={fast} onDownload={download} />}
        {rows.length > 0 && (
          <ol className={styles.queue} aria-label="Queue">
            {rows.map((job) => (
              <QueueRow key={job.id} job={job} arriving={server.initial !== null && !server.initial.has(job.id)} />
            ))}
          </ol>
        )}
      </main>
      {dragging && <div className={styles.frame} aria-hidden="true" data-testid="drag-frame" />}
    </>
  )
}
