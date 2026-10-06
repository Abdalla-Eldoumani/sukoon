import { describe, expect, it } from 'vitest'
import { clock, megabytes, middle } from './format'

describe('format', () => {
  it('writes clock times', () => {
    expect(clock(0)).toBe('0:00')
    expect(clock(65)).toBe('1:05')
    expect(clock(3725)).toBe('1:02:05')
  })

  it('writes sizes', () => {
    expect(megabytes(66_762_490)).toBe('67 MB')
    expect(megabytes(913_106_900)).toBe('913 MB')
    expect(megabytes(2_500_000_000)).toBe('2.50 GB')
  })

  it('cuts long names in the middle', () => {
    const name = 'a'.repeat(40) + '-episode-12-final.mkv'
    const short = middle(name, 30)
    expect(short).toHaveLength(30)
    expect(short.endsWith('final.mkv')).toBe(true)
    expect(middle('short.mp3')).toBe('short.mp3')
  })
})
