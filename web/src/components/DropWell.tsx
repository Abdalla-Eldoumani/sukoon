import { useRef } from 'react'
import styles from './DropWell.module.css'

export const ACCEPT =
  'audio/*,video/*,.mp3,.m4a,.aac,.wav,.flac,.ogg,.opus,.webm,.mp4,.mov,.mkv,.avi'

interface Props {
  compact: boolean
  dragging: boolean
  onFiles: (files: File[]) => void
}

export function DropWell({ compact, dragging, onFiles }: Props) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <section className={compact ? `${styles.well} ${styles.compact}` : styles.well} aria-label="Add files">
      <p className={styles.prompt}>{dragging ? 'Release to add' : 'Drop audio or video here'}</p>
      <button type="button" className="btn-quiet" onClick={() => input.current?.click()}>
        Choose files
      </button>
      {!compact && (
        <p className={`small ${styles.formats}`}>
          MP3, M4A, WAV, FLAC, OGG, Opus, MP4, MOV, MKV, WEBM and most other formats
        </p>
      )}
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          const files = Array.from(e.currentTarget.files ?? [])
          e.currentTarget.value = ''
          if (files.length) onFiles(files)
        }}
      />
    </section>
  )
}
