/** The parts of a media element the sync loop touches. */
export interface Media {
  currentTime: number
  paused: boolean
  play: () => Promise<void> | void
  pause: () => void
}

export const DRIFT_S = 0.04
const MAX_LEAD_S = 0.25

// A seek takes time to land, so a follower set to the clock's time arrives behind it. Each
// follower learns how far ahead to aim from how far off its last correction landed.
const lead = new WeakMap<Media, number>()
const corrected = new WeakMap<Media, boolean>()

/**
 * Pulls each follower back to the clock when it has drifted more than 40 ms, and keeps it
 * playing or paused with the clock. `offset` is where follower time zero sits on the clock.
 */
export function follow(clock: Media, followers: Media[], offset = 0): void {
  const target = clock.currentTime - offset
  for (const media of followers) {
    if (target < 0) {
      // Before the audio starts on the video's timeline: hold at the start, silent.
      if (!media.paused) media.pause()
      media.currentTime = 0
      continue
    }
    const error = media.currentTime - target
    if (corrected.get(media) && !clock.paused) {
      lead.set(media, Math.min(MAX_LEAD_S, Math.max(0, (lead.get(media) ?? 0) - error)))
      corrected.set(media, false)
    }
    if (Math.abs(error) > DRIFT_S) {
      media.currentTime = target + (clock.paused ? 0 : (lead.get(media) ?? 0))
      corrected.set(media, true)
    }
    if (clock.paused && !media.paused) media.pause()
    if (!clock.paused && media.paused) void media.play()
  }
}
