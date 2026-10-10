import { useId, useRef, useState } from 'react'
import styles from './DropWell.module.css'
import { EmptyStrip } from './EmptyStrip'

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

/** Where work comes in: the whole window takes a drop; this holds the button and the link field. */
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
  const size = compact ? ' btn-small' : ''
  const choose = (
    <button
      type="button"
      className={compact ? `btn-quiet${size}` : 'btn-primary'}
      onClick={() => input.current?.click()}
    >
      Choose files
    </button>
  )
  const link = (
    <form
      className={styles.link}
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      <input
        className={compact ? 'input input-small' : 'input'}
        type="url"
        inputMode="url"
        aria-label="Link to a video"
        placeholder={compact ? 'Paste a link' : 'Paste a link from YouTube, X, SoundCloud...'}
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        aria-invalid={linkError ? true : undefined}
        aria-describedby={linkError ? errorId : undefined}
      />
      <button type="submit" className={`btn-quiet${size}`} disabled={sending}>
        Add link
      </button>
    </form>
  )
  const error = linkError && (
    <p id={errorId} className={`small ${styles.error}`}>
      {linkError}
    </p>
  )
  const picker = (
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
  )

  if (compact) {
    return (
      <section className={styles.bar} aria-label="Add files">
        <p className={`body-strong ${styles.lead}`}>{dragging ? 'Release to add' : 'Drop more files anywhere'}</p>
        {choose}
        {link}
        {error}
        {picker}
      </section>
    )
  }
  return (
    <section className={styles.intake} aria-label="Add files">
      <div className={styles.hero}>
        <h2 className="display">{dragging ? 'Release to add.' : 'Drop a recording anywhere.'}</h2>
        <p className={styles.lede}>Keeps the voices and takes out the music, though a little can stay behind. Everything happens on this computer.</p>
        <div className={styles.controls}>
          {choose}
          <span className={styles.or}>or</span>
          {link}
        </div>
        {error}
        <p className={`small ${styles.sites}`}>
          Links work from YouTube, X, Facebook, Reddit, and SoundCloud. Instagram, TikTok, and Vimeo often refuse.
        </p>
      </div>
      <EmptyStrip dragging={dragging} />
      {picker}
    </section>
  )
}
