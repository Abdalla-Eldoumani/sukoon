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
// The lead a pending correction aimed with, until the next playing tick measures where it landed.
const aimed = new WeakMap<Media, number>()

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
    const pending = aimed.get(media)
    if (pending !== undefined && !clock.paused) {
      // Further off than any seek lag means the clock itself moved (the user seeked): not a lesson.
      if (Math.abs(error) <= MAX_LEAD_S) lead.set(media, Math.min(MAX_LEAD_S, Math.max(0, pending - error)))
      aimed.delete(media)
    }
    if (Math.abs(error) > DRIFT_S) {
      const ahead = clock.paused ? 0 : (lead.get(media) ?? 0)
      media.currentTime = target + ahead
      aimed.set(media, ahead)
    }
    if (clock.paused && !media.paused) media.pause()
    if (!clock.paused && media.paused) void media.play()
  }
}
