import { afterEach, describe, expect, it, vi } from 'vitest'
import { applyTheme, followSystem, resolveTheme, storedTheme } from './theme'
import { THEMES } from './themes'
import prePaint from '../../public/theme.js?raw'

type Prefs = { light?: boolean; contrast?: boolean }
let listeners: (() => void)[] = []

function prefer({ light = false, contrast = false }: Prefs) {
  window.matchMedia = vi.fn((query: string) => ({
    matches: (query.includes('light') && light) || (query.includes('contrast') && contrast),
    addEventListener: (_: string, f: () => void) => listeners.push(f),
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia
}

afterEach(() => {
  vi.restoreAllMocks()
  listeners = []
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('theme', () => {
  it('follows the system until a choice is made', () => {
    expect(storedTheme()).toBe('system')
  })

  it('remembers a manual choice and applies it to the page', () => {
    prefer({})
    applyTheme('midnight')
    expect(document.documentElement.dataset.theme).toBe('midnight')
    expect(storedTheme()).toBe('midnight')
    applyTheme('system')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(storedTheme()).toBe('system')
  })

  it('reads System from the computer, and a request for more contrast wins', () => {
    prefer({ light: true })
    expect(resolveTheme('system')).toBe('light')
    prefer({ light: true, contrast: true })
    expect(resolveTheme('system')).toBe('contrast')
    expect(resolveTheme('parchment')).toBe('parchment')
  })

  it('switches with the computer while System is chosen, and not otherwise', () => {
    prefer({})
    applyTheme('system')
    followSystem()
    prefer({ light: true })
    listeners.forEach((f) => f())
    expect(document.documentElement.dataset.theme).toBe('light')
    applyTheme('parchment')
    listeners.forEach((f) => f())
    expect(document.documentElement.dataset.theme).toBe('parchment')
  })

  it('ignores a stored value that is not a theme', () => {
    window.localStorage.setItem('sukoon.theme', 'neon')
    expect(storedTheme()).toBe('system')
  })

  it('falls back to the system theme when storage throws', () => {
    prefer({})
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    expect(storedTheme()).toBe('system')
    expect(() => applyTheme('dark')).not.toThrow()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  // public/theme.js runs before the app loads; it must pick what the app would.
  const cases: [string, Prefs][] = [
    ...THEMES.map((t): [string, Prefs] => [t.id, {}]),
    ['system', { light: true }],
    ['system', { contrast: true }],
    ['neon', {}],
  ]
  it.each(cases)('pre-paints the same palette as the app for %s %o', (stored, prefs) => {
    prefer(prefs)
    if (stored !== 'system') window.localStorage.setItem('sukoon.theme', stored)
    new Function(prePaint)()
    expect(document.documentElement.dataset.theme).toBe(resolveTheme(storedTheme()))
  })

  it('pre-paints from the same list of palettes', () => {
    const listed = JSON.parse(prePaint.match(/ids = (\[[^\]]*\])/)![1].replaceAll("'", '"'))
    expect(listed).toEqual(THEMES.filter((t) => t.id !== 'system').map((t) => t.id))
  })
})
