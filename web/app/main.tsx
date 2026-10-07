import '@fontsource-variable/archivo/wdth.css'
import '@fontsource-variable/martian-mono/wdth.css'
import '@fontsource/ibm-plex-sans-arabic/arabic-400.css'
import '@fontsource/ibm-plex-sans-arabic/arabic-500.css'
import '@fontsource/ibm-plex-sans-arabic/arabic-600.css'
import '../styles/themes.css'
import '../styles/global.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { applyTheme, followSystem, storedTheme } from '../lib/theme/theme'

applyTheme(storedTheme())
followSystem()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
