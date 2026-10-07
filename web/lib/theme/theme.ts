import { THEMES, type Palette, type Theme } from './themes'

export type { Palette, Theme } from './themes'

const KEY = 'sukoon.theme'
const IDS: readonly string[] = THEMES.map((t) => t.id)

function matches(query: string): boolean {
  return window.matchMedia?.(query).matches ?? false
}

// Storage can be missing or throw (private windows, blocked site data); the system theme stands in.
export function storedTheme(): Theme {
  try {
    const value = window.localStorage.getItem(KEY)
    return value && IDS.includes(value) ? (value as Theme) : 'system'
  } catch {
    return 'system'
  }
}

/** The palette a choice stands for. System asks the computer, and asking for more contrast wins. */
export function resolveTheme(theme: Theme): Palette {
  if (theme !== 'system') return theme
  if (matches('(prefers-contrast: more)')) return 'contrast'
  return matches('(prefers-color-scheme: light)') ? 'light' : 'dark'
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', resolveTheme(theme))
  try {
    if (theme === 'system') window.localStorage.removeItem(KEY)
    else window.localStorage.setItem(KEY, theme)
  } catch {
    // Nothing to do: the choice still applies to this page.
  }
}

/** Keeps System in step when the computer switches between light and dark. */
export function followSystem(): () => void {
  const queries = ['(prefers-color-scheme: light)', '(prefers-contrast: more)'].map((q) => window.matchMedia?.(q))
  const update = () => {
    if (storedTheme() === 'system') applyTheme('system')
  }
  queries.forEach((q) => q?.addEventListener('change', update))
  return () => queries.forEach((q) => q?.removeEventListener('change', update))
}
