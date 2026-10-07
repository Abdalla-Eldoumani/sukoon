import styles from './EmptyStrip.module.css'

/** Where the queue will be: the strip every file gets, with nothing in it yet. */
export function EmptyStrip({ dragging }: { dragging: boolean }) {
  return (
    <figure className={styles.strip} data-dragging={dragging || undefined}>
      <span className={`small ${styles.voice}`}>Voice kept</span>
      <span className={styles.line} />
      <span className={`small ${styles.removed}`}>Music removed</span>
      <figcaption className={`small ${styles.caption}`}>
        Each file you add gets a strip like this one, with the voice kept above the line and the music removed below it.
      </figcaption>
    </figure>
  )
}
