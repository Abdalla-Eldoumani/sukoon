import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { getJson, postJson, putJson, request, type Health, type Settings } from '../lib/api/client'
import styles from './App.module.css'
import { ClearFinished } from '../components/queue/ClearFinished'
import { DropWell } from '../components/queue/DropWell'
import { LiveRegion } from '../components/chrome/LiveRegion'
import { ReviewPanel } from '../components/review/ReviewPanel'
import { SettingsSheet } from '../components/chrome/SettingsSheet'
import { SetupScreen } from '../components/chrome/SetupScreen'
import { ModelCard } from '../components/chrome/ModelCard'
import { QueueRow, type RowActions } from '../components/queue/QueueRow'
import { TopBar } from '../components/chrome/TopBar'
import { useServerState } from '../lib/api/server-state'
import type { Job, Preset } from '../lib/api/types'
import { reducedMotion } from '../lib/motion'
import { uploadFile } from '../lib/api/upload'
import { useWindowDrag } from '../lib/hooks/use-window-drag'

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
    link: null,
    through: null,
  }
}

/** The values `from` holds for the keys a change touched. */
function pick(from: Settings, change: Partial<Settings>): Partial<Settings> {
  return Object.fromEntries(Object.keys(change).map((k) => [k, from[k as keyof Settings]]))
}

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const server = useServerState()
  const [uploads, setUploads] = useState<Job[]>([])
  const queue = useRef(Promise.resolve())
  const counter = useRef(0)
  const [problems, setProblems] = useState<Record<string, string>>({})
  const [library, setLibrary] = useState<{ jobs: number; models: number } | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [checking, setChecking] = useState(false)
  const [clearError, setClearError] = useState<string | null>(null)
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

  const [linkError, setLinkError] = useState<string | null>(null)
  const addLink = useCallback(async (url: string) => {
    setLinkError(null)
    try {
      await postJson('/api/links', { url })
      return true
    } catch (e) {
      setLinkError((e as Error).message)
      return false
    }
  }, [])
  // A link pasted anywhere but a text field starts a job, so Ctrl+V is all it takes.
  useEffect(() => {
    const paste = (e: ClipboardEvent) => {
      const target = e.target as HTMLElement | null
      if (target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)) return
      const text = e.clipboardData?.getData('text/plain').trim() ?? ''
      if (!/^https?:\/\/\S+$/i.test(text)) return
      e.preventDefault()
      void addLink(text)
    }
    window.addEventListener('paste', paste)
    return () => window.removeEventListener('paste', paste)
  }, [addLink])

  const [settingsError, setSettingsError] = useState<string | null>(null)
  const checkHealth = useCallback(() => {
    setChecking(true)
    getJson<Health>('/api/health')
      .then((h) => {
        setHealth(h)
        // The encoders are only known once ffmpeg is there, so the format lists change too.
        if (h.ffmpeg.ok) getJson<Settings>('/api/settings').then(setSettings, () => {})
      })
      // A failed check keeps whatever was known; it must not drop the setup screen.
      .catch(() => {})
      .finally(() => setChecking(false))
  }, [])
  useEffect(() => {
    getJson<Health>('/api/health').then(setHealth, () => setHealth(null))
    getJson<Settings>('/api/settings').then(setSettings, () => setSettings(null))
  }, [])

  // Shown at once so the controls never lag the keys. Only the newest save's answer is applied;
  // after a refusal the server's own copy is read back, since a later save may have changed it.
  const lastSave = useRef(0)
  const changeSettings = (values: Partial<Settings>) => {
    const turn = ++lastSave.current
    const before = settings
    setSettingsError(null)
    setSettings((s) => (s ? { ...s, ...values } : s))
    putJson<Settings>('/api/settings', values).then(
      (saved) => {
        if (turn === lastSave.current) setSettings(saved)
        if ('device' in values) checkHealth()
      },
      (e: Error) => {
        setSettingsError(e.message)
        if (turn !== lastSave.current) return
        getJson<Settings>('/api/settings').then(
          (current) => {
            if (turn === lastSave.current) setSettings(current)
          },
          // Unreachable too: put back only what this change touched.
          () => setSettings((s) => (s && before ? { ...s, ...pick(before, values) } : s)),
        )
      },
    )
  }
  // The sheet slides with a view transition where the browser has one.
  const toggleSheet = (open: boolean) => {
    const change = () => setSheetOpen(open)
    if (document.startViewTransition && !reducedMotion()) document.startViewTransition(() => flushSync(change))
    else change()
  }
  const closeSheet = useCallback(() => toggleSheet(false), [])

  // The library only changes size when a job finishes or goes away.
  const settled = server.jobs
    .filter((j) => ['done', 'failed', 'canceled', 'interrupted'].includes(j.state))
    .map((j) => j.id)
    .join()
  useEffect(() => {
    if (!server.connected) return
    getJson<{ jobs: number; models: number }>('/api/library').then(setLibrary, () => setLibrary(null))
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
    if (document.startViewTransition && !reducedMotion()) document.startViewTransition(() => flushSync(change))
    else change()
  }
  const finished = server.jobs.filter((j) => ['done', 'failed', 'canceled', 'interrupted'].includes(j.state))
  const clearFinished = () => {
    setClearError(null)
    postJson('/api/library/clear').catch((e: Error) => setClearError(e.message))
  }

  const [downloadError, setDownloadError] = useState<string | null>(null)
  const download = (preset: Preset, switchJobs: boolean) => {
    setDownloadError(null)
    request(`/api/models/${preset}/download${switchJobs ? '?switch=1' : ''}`, { method: 'POST' }).catch((e: Error) =>
      setDownloadError(e.message),
    )
    // Choosing Fast on the card makes it the default for files added later too.
    if (switchJobs) changeSettings({ preset })
  }

  const uploadingNames = new Set(uploads.filter((u) => u.state === 'uploading').map((u) => u.name))
  const rows = [...server.jobs.filter((j) => !(j.state === 'checking' && uploadingNames.has(j.name))), ...uploads]
  const best = server.models.find((m) => m.preset === 'best')
  const fast = server.models.find((m) => m.preset === 'fast')
  const needsModel =
    server.jobs.some((j) => j.state === 'waiting_model') || server.models.some((m) => m.downloading || m.error)

  if (health && !health.ffmpeg.ok) {
    return (
      <>
        <TopBar device={health.device} library={null} />
        <SetupScreen install={health.ffmpeg.install} checking={checking} onCheck={checkHealth} />
      </>
    )
  }

  return (
    <>
      <TopBar
        device={health?.device ?? null}
        library={library?.jobs ?? null}
        onSettings={settings ? () => toggleSheet(true) : null}
      />
      <main className={styles.main}>
        {rows.length === 0 && (
          <DropWell compact={false} dragging={dragging} onFiles={addFiles} onLink={addLink} linkError={linkError} />
        )}
        {rows.length > 0 && (
          <div className={styles.intakeBar}>
            <DropWell compact dragging={dragging} onFiles={addFiles} onLink={addLink} linkError={linkError} />
            {finished.length > 0 && <ClearFinished count={finished.length} error={clearError} onClear={clearFinished} />}
          </div>
        )}
        {needsModel && best && fast && (
          <ModelCard
            best={best}
            fast={fast}
            onDownload={download}
            problem={downloadError}
            primary={rows.length > 0 && reviewing === null}
          />
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
      {sheetOpen && settings && (
        <SettingsSheet
          settings={settings}
          library={library}
          error={settingsError}
          onChange={changeSettings}
          onClearFinished={clearFinished}
          onClose={closeSheet}
        />
      )}
      {dragging && <div className={styles.frame} aria-hidden="true" data-testid="drag-frame" />}
    </>
  )
}
