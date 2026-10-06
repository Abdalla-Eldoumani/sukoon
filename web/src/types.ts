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
  default: boolean
}

export interface FormatChoice {
  value: string
  video: boolean
  reencode: boolean
  /** The ffmpeg encoder this format needs and lacks, if any. */
  missing: string | null
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
  options: { preset: Preset; format: string | null; track: number | null; reencode_ok?: boolean }
  duration: number | null
  tracks: Track[]
  notes: string[]
  formats: FormatChoice[]
  /** Where the audio previews start on the video's timeline, in seconds. */
  offset: number
  confirm: string | null
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
