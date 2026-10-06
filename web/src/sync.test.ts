import { describe, expect, it } from 'vitest'
import { follow, type Media } from './sync'

class FakeMedia implements Media {
  currentTime = 0
  paused = true
  constructor(public rate = 1) {}
  play() {
    this.paused = false
  }
  pause() {
    this.paused = true
  }
  advance(seconds: number) {
    if (!this.paused) this.currentTime += seconds * this.rate
  }
}

describe('follow', () => {
  it('keeps followers within 40 ms of the clock over minutes of drift', () => {
    const clock = new FakeMedia(1)
    const fast = new FakeMedia(1.004)
    const slow = new FakeMedia(0.996)
    for (const m of [clock, fast, slow]) m.play()
    let worst = 0
    for (let tick = 0; tick < 4 * 60 * 5; tick++) {
      // Every 250 ms, as the player does.
      for (const m of [clock, fast, slow]) m.advance(0.25)
      worst = Math.max(worst, Math.abs(fast.currentTime - clock.currentTime), Math.abs(slow.currentTime - clock.currentTime))
      follow(clock, [fast, slow])
    }
    expect(clock.currentTime).toBeCloseTo(300, 5)
    // Corrected past 40 ms, so the worst is 40 ms plus one tick: still under a frame at 24 fps.
    expect(worst).toBeLessThan(1 / 24)
    expect(fast.paused).toBe(false)
  })

  it('leaves small differences alone so playback does not stutter', () => {
    const clock = Object.assign(new FakeMedia(), { currentTime: 10 })
    const follower = Object.assign(new FakeMedia(), { currentTime: 10.03 })
    follow(clock, [follower])
    expect(follower.currentTime).toBe(10.03)
  })

  it('places audio that starts after the picture at the right moment', () => {
    const video = Object.assign(new FakeMedia(), { currentTime: 3, paused: false })
    const audio = new FakeMedia()
    follow(video, [audio], 0.5)
    expect(audio.currentTime).toBe(2.5)
    expect(audio.paused).toBe(false)
    video.currentTime = 0.2
    follow(video, [audio], 0.5)
    expect(audio.currentTime).toBe(0)
    expect(audio.paused).toBe(true)
  })

  it('pauses followers with the clock', () => {
    const clock = new FakeMedia()
    const follower = Object.assign(new FakeMedia(), { paused: false })
    follow(clock, [follower])
    expect(follower.paused).toBe(true)
  })
})
