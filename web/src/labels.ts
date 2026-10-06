import type { JobState } from './types'

export const STATE_LABEL: Record<JobState, string> = {
  uploading: 'Checking',
  fetching: 'Fetching',
  checking: 'Checking',
  awaiting_track: 'Choose track',
  awaiting_confirm: 'Confirm',
  queued: 'Queued',
  waiting_model: 'Waiting for model',
  decoding: 'Decoding',
  separating: 'Separating',
  encoding: 'Encoding',
  done: 'Done',
  failed: 'Failed',
  canceled: 'Canceled',
  interrupted: 'Interrupted',
}

export const ACTIVE: ReadonlySet<JobState> = new Set(['uploading', 'fetching', 'checking', 'decoding', 'separating', 'encoding'])
