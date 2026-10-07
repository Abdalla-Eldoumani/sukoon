import { useEffect, useRef } from 'react'
import { STATE_LABEL } from '../../lib/text/labels'
import type { Job } from '../../lib/api/types'

/** Reads out state changes and every tenth of progress, politely, so screen readers keep up. */
export function LiveRegion({ jobs }: { jobs: Job[] }) {
  const region = useRef<HTMLDivElement>(null)
  const last = useRef(new Map<string, string>())

  useEffect(() => {
    const said: string[] = []
    for (const job of jobs) {
      const step = Math.floor(job.progress * 10)
      const key = `${job.state}:${job.state === 'separating' || job.state === 'decoding' || job.state === 'encoding' ? step : ''}`
      const before = last.current.get(job.id)
      last.current.set(job.id, key)
      if (before === undefined || before === key) continue
      const label = STATE_LABEL[job.state]
      said.push(key.endsWith(':') ? `${job.name}: ${label}` : `${job.name}: ${label}, ${step * 10}%`)
    }
    if (said.length && region.current) region.current.textContent = said.join('. ')
  }, [jobs])

  return <div ref={region} className="visually-hidden" role="status" aria-live="polite" />
}
