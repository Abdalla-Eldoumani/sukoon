import { afterEach, describe, expect, it, vi } from 'vitest'
import { applyTheme, storedTheme } from './theme'

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('theme', () => {
  it('follows the system until a choice is made', () => {
    expect(storedTheme()).toBe('system')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('remembers a manual choice and applies it to the page', () => {
    applyTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(storedTheme()).toBe('light')
    applyTheme('system')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
    expect(storedTheme()).toBe('system')
  })

  it('falls back to the system theme when storage throws', () => {
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
})
