export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const rest = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${rest}` : `${m}:${rest}`
}

export function megabytes(bytes: number): string {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${Math.round(bytes / 1e6)} MB`
}

/** Keeps the start and the end of a long name, where people look for what tells files apart. */
export function middle(name: string, max = 56): string {
  if (name.length <= max) return name
  const keep = max - 1
  const head = Math.ceil(keep * 0.6)
  return `${name.slice(0, head)}…${name.slice(name.length - (keep - head))}`
}
