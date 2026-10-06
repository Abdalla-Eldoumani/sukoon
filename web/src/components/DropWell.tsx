import { useId, useRef, useState } from 'react'
import styles from './DropWell.module.css'

export const ACCEPT =
  'audio/*,video/*,.mp3,.m4a,.aac,.wav,.flac,.ogg,.opus,.webm,.mp4,.mov,.mkv,.avi'

interface Props {
  compact: boolean
  dragging: boolean
  onFiles: (files: File[]) => void
  /** Resolves true when the link became a job; the field clears then. */
  onLink: (url: string) => Promise<boolean>
  /** Why the last link was refused, shown under the field. */
  linkError?: string | null
}

export function DropWell({ compact, dragging, onFiles, onLink, linkError = null }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [url, setUrl] = useState('')
  const [sending, setSending] = useState(false)
  const errorId = useId()
  const submit = async () => {
    if (!url.trim() || sending) return
    setSending(true)
    if (await onLink(url.trim())) setUrl('')
    setSending(false)
  }
  return (
    <section className={compact ? `${styles.well} ${styles.compact}` : styles.well} aria-label="Add files">
      <p className={styles.prompt}>{dragging ? 'Release to add' : 'Drop audio or video here'}</p>
      <button type="button" className="btn-quiet" onClick={() => input.current?.click()}>
        Choose files
      </button>
      <form
        className={styles.link}
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <input
          className="input"
          type="url"
          inputMode="url"
          aria-label="Link to a video"
          placeholder="or paste a link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          aria-invalid={linkError ? true : undefined}
          aria-describedby={linkError ? errorId : undefined}
        />
        <button type="submit" className="btn-quiet" disabled={sending}>
          Add link
        </button>
      </form>
      {linkError && (
        <p id={errorId} className={`small ${styles.error}`}>
          {linkError}
        </p>
      )}
      {!compact && (
        <p className={`small ${styles.formats}`}>
          MP3, M4A, WAV, FLAC, OGG, Opus, MP4, MOV, MKV, WEBM and most other formats, or a link from YouTube, X,
          Instagram, TikTok, Facebook, Reddit, Vimeo, or SoundCloud
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
