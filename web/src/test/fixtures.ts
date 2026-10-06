import type { Job, ModelState } from '../types'

export function job(fields: Partial<Job> = {}): Job {
  return {
    id: 'a1',
    created: 1,
    name: 'lecture.mp3',
    kind: 'audio',
    state: 'queued',
    progress: 0,
    eta: null,
    error: null,
    retryable: true,
    options: { preset: 'best', format: null, track: null },
    duration: 125,
    tracks: [],
    notes: [],
    formats: [],
    offset: 0,
    confirm: null,
    output_name: null,
    link: null,
    ...fields,
  }
}

export function model(fields: Partial<ModelState> = {}): ModelState {
  return {
    preset: 'best',
    ready: false,
    size: 913_107_844,
    downloading: false,
    done: 0,
    rate: 0,
    error: null,
    ...fields,
  }
}

/** Stands in for the browser's EventSource so tests can push server events. */
export class FakeEventSource {
  static last: FakeEventSource | null = null
  static readonly CLOSED = 2
  readyState = 1
  onerror: (() => void) | null = null
  listeners = new Map<string, ((e: MessageEvent) => void)[]>()

  constructor(public url: string) {
    FakeEventSource.last = this
  }

  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn])
  }

  emit(type: string, data: unknown) {
    for (const fn of this.listeners.get(type) ?? []) fn(new MessageEvent(type, { data: JSON.stringify(data) }))
  }

  close() {
    this.readyState = 2
  }
}
