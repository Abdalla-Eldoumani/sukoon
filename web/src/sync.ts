/** The parts of a media element the sync loop touches. */
export interface Media {
  currentTime: number
  paused: boolean
  play: () => Promise<void> | void
  pause: () => void
}

export const DRIFT_S = 0.04

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
    if (Math.abs(media.currentTime - target) > DRIFT_S) media.currentTime = target
    if (clock.paused && !media.paused) media.pause()
    if (!clock.paused && media.paused) void media.play()
  }
}
