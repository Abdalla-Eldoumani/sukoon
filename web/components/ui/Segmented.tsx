import { useRadioArrows } from '../../lib/hooks/use-radio-arrows'
import styles from './Segmented.module.css'

interface Props<T extends string> {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}

/** A radio group drawn as one control; the arrow keys move the choice. */
export function Segmented<T extends string>({ label, value, options, onChange }: Props<T>) {
  const arrows = useRadioArrows(
    options.length,
    options.findIndex((o) => o.value === value),
    (i) => onChange(options[i].value),
  )
  return (
    <div className={styles.group} role="radiogroup" aria-label={label} {...arrows}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          className={styles.segment}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
