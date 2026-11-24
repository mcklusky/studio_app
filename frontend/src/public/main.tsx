import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Fonts are bundled (no third-party font requests), the same as the staff app.
import '@fontsource/dm-sans/latin-400.css'
import '@fontsource/dm-sans/latin-500.css'
import '@fontsource/dm-sans/latin-700.css'
import '@fontsource/manrope/latin-600.css'
import '@fontsource/manrope/latin-700.css'
import '@fontsource/manrope/latin-800.css'
import './public.css'
import { setupInstall } from '../lib/install'
import { PublicSite } from './PublicSite'

setupInstall()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PublicSite />
  </StrictMode>,
)
