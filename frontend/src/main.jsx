import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import AuthShell from './AuthShell.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthShell />
  </StrictMode>,
)
