export type Theme = 'system' | 'dark' | 'light'

const KEY = 'sukoon.theme'

// Storage can be missing or throw (private windows, blocked site data); the system theme stands in.
export function storedTheme(): Theme {
  try {
    const value = window.localStorage.getItem(KEY)
    return value === 'dark' || value === 'light' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  try {
    if (theme === 'system') window.localStorage.removeItem(KEY)
    else window.localStorage.setItem(KEY, theme)
  } catch {
    // Nothing to do: the choice still applies to this page.
  }
}
