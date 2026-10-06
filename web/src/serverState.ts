import { useEffect, useState } from 'react'
import type { Job, ModelState } from './types'

export interface ServerState {
  jobs: Job[]
  models: ModelState[]
  connected: boolean
}

function byCreated(a: Job, b: Job) {
  return a.created - b.created
}

/** Jobs and model downloads as the server reports them, kept current by the event stream. */
export function useServerState(): ServerState {
  const [state, setState] = useState<ServerState>({ jobs: [], models: [], connected: false })

  useEffect(() => {
    let source: EventSource | null = null
    let retry = 1000
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false

    const connect = () => {
      source = new EventSource('/api/events')
      source.addEventListener('snapshot', (e) => {
        const data = JSON.parse((e as MessageEvent).data) as { jobs: Job[]; models: ModelState[] }
        retry = 1000
        setState({ jobs: data.jobs.sort(byCreated), models: data.models, connected: true })
      })
      source.addEventListener('job', (e) => {
        const job = JSON.parse((e as MessageEvent).data) as Job
        setState((s) => ({
          ...s,
          jobs: [...s.jobs.filter((j) => j.id !== job.id), job].sort(byCreated),
        }))
      })
      source.addEventListener('deleted', (e) => {
        const { id } = JSON.parse((e as MessageEvent).data) as { id: string }
        setState((s) => ({ ...s, jobs: s.jobs.filter((j) => j.id !== id) }))
      })
      source.addEventListener('model', (e) => {
        const model = JSON.parse((e as MessageEvent).data) as ModelState
        setState((s) => ({ ...s, models: s.models.map((m) => (m.preset === model.preset ? model : m)) }))
      })
      source.onerror = () => {
        setState((s) => ({ ...s, connected: false }))
        // The browser retries on its own unless the stream closed for good.
        if (source?.readyState === EventSource.CLOSED && !stopped) {
          source.close()
          timer = setTimeout(connect, retry)
          retry = Math.min(retry * 2, 10_000)
        }
      }
    }
    connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      source?.close()
    }
  }, [])

  return state
}
