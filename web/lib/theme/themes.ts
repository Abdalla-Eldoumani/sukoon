/** The themes in the picker, in order. Their colours are in styles/themes.css. */
export const THEMES = [
  { id: 'system', name: 'System', note: 'Follows your computer' },
  { id: 'dark', name: 'Night', note: 'Warm graphite' },
  { id: 'light', name: 'Day', note: 'Cool aluminium' },
  { id: 'contrast', name: 'High contrast', note: 'Black and white' },
  { id: 'parchment', name: 'Parchment', note: 'Warm paper' },
  { id: 'midnight', name: 'Midnight', note: 'Blue-black' },
] as const

export type Theme = (typeof THEMES)[number]['id']
/** A theme with its own colours: every theme but System. */
export type Palette = Exclude<Theme, 'system'>
