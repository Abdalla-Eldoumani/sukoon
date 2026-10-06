import styles from './SetupScreen.module.css'

interface Props {
  install: string
  checking: boolean
  onCheck: () => void
}

/** Shown instead of everything else while ffmpeg is missing, since nothing works without it. */
export function SetupScreen({ install, checking, onCheck }: Props) {
  return (
    <main className={styles.screen}>
      <h2 className="display">sukoon needs ffmpeg.</h2>
      <p className={styles.text}>ffmpeg reads and writes the audio and video. Install it with this command, then check again.</p>
      <code className={`readout ${styles.command}`}>{install}</code>
      <button type="button" className="btn-primary" onClick={onCheck} disabled={checking}>
        Check again
      </button>
    </main>
  )
}
