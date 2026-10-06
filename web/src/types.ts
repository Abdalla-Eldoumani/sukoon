export type JobState =
  | 'uploading'
  | 'checking'
  | 'awaiting_track'
  | 'awaiting_confirm'
  | 'queued'
  | 'waiting_model'
  | 'decoding'
  | 'separating'
  | 'encoding'
  | 'done'
  | 'failed'
  | 'canceled'
  | 'interrupted'

export type Preset = 'best' | 'fast'

export interface Track {
  language: string | null
  title: string | null
  channels: number | null
}

export interface Job {
  id: string
  created: number
  name: string
  kind: 'audio' | 'video' | null
  state: JobState
  progress: number
  eta: number | null
  error: string | null
  retryable: boolean
  options: { preset: Preset; format: string | null; track: number | null }
  duration: number | null
  tracks: Track[]
  notes: string[]
  output_name: string | null
}

export interface ModelState {
  preset: Preset
  ready: boolean
  size: number
  downloading: boolean
  done: number
  rate: number
  error: string | null
}
