import { useRef, type KeyboardEvent } from 'react'
import { THEMES, type Palette, type Theme } from '../../lib/theme/themes'
import styles from './ThemePicker.module.css'

// One short stretch of a strip: voice heights above the line, removed-music heights below.
const VOICE = [3, 6, 9, 5, 2, 7, 10, 8, 4, 2, 5, 9, 6, 3]
const MUSIC = [5, 4, 6, 5, 7, 6, 5, 4, 6, 7, 5, 4, 6, 5]

function Sample({ palette, half }: { palette: Palette; half?: 'left' | 'right' }) {
  return (
    <span className={styles.sample} data-theme={palette} data-half={half}>
      <svg viewBox="0 0 56 24" aria-hidden="true">
        <line x1="0" y1="12" x2="56" y2="12" className={styles.line} />
        {VOICE.map((h, i) => (
          <rect key={`v${i}`} x={i * 4} y={12 - h} width="2.5" height={h} className={styles.voice} />
        ))}
        {MUSIC.map((h, i) => (
          <rect key={`m${i}`} x={i * 4} y={12.5} width="2.5" height={h * 0.9} className={styles.removed} />
        ))}
      </svg>
    </span>
  )
}

interface Props {
  value: Theme
  onChange: (theme: Theme) => void
}

/** Each theme as a swatch drawn in its own colours; a radio group, so the arrow keys move the choice. */
export function ThemePicker({ value, onChange }: Props) {
  const group = useRef<HTMLDivElement>(null)
  const onKeyDown = (e: KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key]
    if (!step) return
    e.preventDefault()
    const at = THEMES.findIndex((t) => t.id === value)
    const next = (at + step + THEMES.length) % THEMES.length
    onChange(THEMES[next].id)
    group.current?.querySelectorAll<HTMLButtonElement>('[role=radio]')[next]?.focus()
  }
  return (
    <div ref={group} className={styles.grid} role="radiogroup" aria-label="Theme" onKeyDown={onKeyDown}>
      {THEMES.map((t) => (
        <button
          key={t.id}
          type="button"
          role="radio"
          aria-checked={t.id === value}
          aria-description={t.note}
          tabIndex={t.id === value ? 0 : -1}
          className={styles.swatch}
          onClick={() => onChange(t.id)}
        >
          <span className={styles.preview}>
            {t.id === 'system' ? (
              <>
                <Sample palette="dark" half="left" />
                <Sample palette="light" half="right" />
              </>
            ) : (
              <Sample palette={t.id} />
            )}
          </span>
          <span className={styles.name}>{t.name}</span>
        </button>
      ))}
    </div>
  )
}
