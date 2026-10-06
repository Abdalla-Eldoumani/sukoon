import { useEffect, useState } from 'react'
import { getJson, type Health } from './api'
import styles from './App.module.css'
import { DropWell } from './components/DropWell'
import { TopBar } from './components/TopBar'
import { useWindowDrag } from './useWindowDrag'

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const addFiles = () => {}
  const dragging = useWindowDrag(addFiles)

  useEffect(() => {
    getJson<Health>('/api/health').then(setHealth, () => setHealth(null))
  }, [])

  return (
    <>
      <TopBar device={health?.device ?? null} />
      <main className={styles.main}>
        <DropWell compact={false} dragging={dragging} onFiles={addFiles} />
        <p className={styles.note}>
          Voices stay. Instruments, and most other non-voice sounds, are removed. Everything happens
          on this computer.
        </p>
      </main>
      {dragging && <div className={styles.frame} aria-hidden="true" />}
    </>
  )
}
