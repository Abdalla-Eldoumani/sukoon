import { useCallback, useEffect, useRef, useState } from 'react'
import { loadPeaks } from '../lanes'
import { follow, type Media } from '../sync'
import type { Job } from '../types'
import styles from './ReviewPanel.module.css'
import { Strip, type Peaks } from './Strip'
import { Transport } from './Transport'

const TICK_MS = 250

function typing(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName) || target.isContentEditable)
  )
}

/** Plays a finished job: the cleaned audio, the original at the same moment, and the strip. */
export function ReviewPanel({ job }: { job: Job }) {
  const [peaks, setPeaks] = useState<Peaks | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [videoBroken, setVideoBroken] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [original, setOriginal] = useState(false)
  const [held, setHeld] = useState(false)
  const clean = useRef<HTMLAudioElement>(null)
  const source = useRef<HTMLAudioElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const hasVideo = job.kind === 'video' && !videoBroken
  const offset = hasVideo ? job.offset : 0
  const hearOriginal = original || held

  useEffect(() => {
    loadPeaks(job.id).then(setPeaks, (e: Error) => setFailed(e.message))
  }, [job.id])

  // Only one of the two previews is audible; both always play, so switching is instant.
  useEffect(() => {
    if (clean.current) clean.current.muted = hearOriginal
    if (source.current) source.current.muted = !hearOriginal
  }, [hearOriginal])

  // Video is the clock when there is one; otherwise the preview being heard leads, so the
  // one that gets nudged is always the muted one.
  const parts = useCallback(() => {
    const audible = hearOriginal ? source.current : clean.current
    const muted = hearOriginal ? clean.current : source.current
    const audios = [audible, muted].filter((m): m is HTMLAudioElement => m !== null)
    const leader: Media | null = hasVideo ? video.current : audible
    const followers: Media[] = hasVideo ? audios : audios.slice(1)
    return { leader, followers }
  }, [hasVideo, hearOriginal])

  useEffect(() => {
    const timer = setInterval(() => {
      const { leader, followers } = parts()
      if (!leader) return
      follow(leader, followers, offset)
      setCurrent(Math.max(0, leader.currentTime - offset))
      setPlaying(!leader.paused)
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [parts, offset])

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      // Copy shortcuts are not a compare; macOS sends no keyup for C while Cmd is down.
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if ((e.key === 'c' || e.key === 'C') && !e.repeat && !typing(e.target)) setHeld(true)
    }
    const up = (e: KeyboardEvent) => {
      if (e.key === 'c' || e.key === 'C') setHeld(false)
    }
    // A key released while the window is elsewhere never reaches us.
    const letGo = () => setHeld(false)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', letGo)
    document.addEventListener('visibilitychange', letGo)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', letGo)
      document.removeEventListener('visibilitychange', letGo)
    }
  }, [])

  const seek = (seconds: number) => {
    const { leader, followers } = parts()
    if (!leader) return
    leader.currentTime = seconds + offset
    follow(leader, followers, offset)
    setCurrent(seconds)
  }
  const play = () => {
    const { leader, followers } = parts()
    if (!leader) return
    void leader.play()
    const target = leader.currentTime - offset
    for (const f of followers) {
      if (target < 0) continue
      f.currentTime = target
      void f.play()
    }
    setPlaying(true)
  }
  const pause = () => {
    const { leader, followers } = parts()
    leader?.pause()
    for (const f of followers) f.pause()
    setPlaying(false)
  }

  return (
    <section className={hasVideo ? `${styles.panel} ${styles.withVideo}` : styles.panel} aria-label={`Review ${job.name}`}>
      {hasVideo && (
        <video
          ref={video}
          className={styles.video}
          src={`/api/jobs/${job.id}/source`}
          muted
          playsInline
          preload="metadata"
          onError={() => setVideoBroken(true)}
          onEnded={() => setPlaying(false)}
        />
      )}
      <div className={styles.evidence}>
        {job.kind === 'video' && videoBroken && (
          <p className={`small ${styles.note}`}>Your browser can&rsquo;t preview this video; the downloaded file is fine.</p>
        )}
        <audio ref={clean} src={`/api/jobs/${job.id}/preview/clean`} preload="auto" onEnded={() => setPlaying(false)} />
        <audio ref={source} src={`/api/jobs/${job.id}/preview/original`} preload="auto" muted />
        {failed && <p className={`small ${styles.error}`}>{failed}</p>}
        {peaks && <Strip peaks={peaks} current={current} onSeek={seek} />}
        <div className={styles.controls}>
          <Transport
            playing={playing}
            current={current}
            duration={peaks?.seconds ?? job.duration ?? 0}
            original={hearOriginal}
            onPlay={play}
            onPause={pause}
            onToggle={() => setOriginal((o) => !o)}
            onHold={setHeld}
          />
          {job.output_name && (
            <a className="btn-primary" href={`/api/jobs/${job.id}/output`} download={job.output_name}>
              Download
            </a>
          )}
        </div>
      </div>
    </section>
  )
}
