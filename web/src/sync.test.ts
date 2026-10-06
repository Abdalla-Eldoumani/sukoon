import { describe, expect, it } from 'vitest'
import { follow, type Media } from './sync'

class FakeMedia implements Media {
  paused = true
  seeks = 0
  private time = 0
  private stalled = 0
  /** `seekLag` is how long a seek takes to land, during which the media does not advance. */
  constructor(
    public rate = 1,
    public seekLag = 0,
  ) {}
  get currentTime() {
    return this.time
  }
  set currentTime(value: number) {
    this.time = value
    this.stalled = this.seekLag
    this.seeks += 1
  }
  play() {
    this.paused = false
  }
  pause() {
    this.paused = true
  }
  advance(seconds: number) {
    if (this.paused) return
    const stall = Math.min(this.stalled, seconds)
    this.stalled -= stall
    this.time += (seconds - stall) * this.rate
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

  it('settles instead of seeking on every tick when seeks take time to land', () => {
    const clock = new FakeMedia(1)
    const follower = new FakeMedia(1.002, 0.042)
    for (const m of [clock, follower]) m.play()
    follower.currentTime = 0.1 // start well off, so a correction is needed
    follower.seeks = 0
    let late = 0
    for (let tick = 0; tick < 4 * 60; tick++) {
      for (const m of [clock, follower]) m.advance(0.25)
      if (tick > 20) late = Math.max(late, Math.abs(follower.currentTime - clock.currentTime))
      follow(clock, [follower])
    }
    // A minute of playback: a few corrections at the start, then one only as drift builds up.
    expect(follower.seeks).toBeLessThan(10)
    expect(late).toBeLessThan(1 / 24)
  })

  it('does not mistake a seek by the user for a correction that landed badly', () => {
    const clock = new FakeMedia(1)
    const follower = new FakeMedia(1, 0.042)
    for (const m of [clock, follower]) m.play()
    const tick = () => {
      for (const m of [clock, follower]) m.advance(0.25)
      follow(clock, [follower])
    }
    follower.currentTime = 0.1
    for (let i = 0; i < 40; i++) tick()
    // A correction is pending when the user jumps ahead five seconds.
    follower.currentTime = clock.currentTime + 0.1
    follow(clock, [follower])
    clock.currentTime += 5
    tick()
    tick()
    expect(Math.abs(follower.currentTime - clock.currentTime)).toBeLessThan(1 / 24)
  })

  it('leaves small differences alone so playback does not stutter', () => {
    const clock = new FakeMedia()
    clock.currentTime = 10
    const follower = new FakeMedia()
    follower.currentTime = 10.03
    follower.seeks = 0
    follow(clock, [follower])
    expect(follower.currentTime).toBe(10.03)
    expect(follower.seeks).toBe(0)
  })

  it('places audio that starts after the picture at the right moment', () => {
    const video = new FakeMedia()
    video.currentTime = 3
    video.play()
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
    const follower = new FakeMedia()
    follower.play()
    follow(clock, [follower])
    expect(follower.paused).toBe(true)
  })
})
