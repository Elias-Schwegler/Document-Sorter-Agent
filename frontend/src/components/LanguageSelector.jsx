import { useState, useRef, useEffect } from 'react'
import { Globe } from 'lucide-react'
import { useI18n, LANGUAGES } from '../i18n'
import './LanguageSelector.css'

export default function LanguageSelector() {
  const { lang, setLanguage } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const current = LANGUAGES.find(l => l.code === lang) || LANGUAGES[0]

  return (
    <div className="lang-selector" ref={ref}>
      <button className="lang-btn" onClick={() => setOpen(!open)} title="Language">
        <Globe size={16} />
        <span>{current.flag}</span>
      </button>
      {open && (
        <div className="lang-dropdown">
          {LANGUAGES.map(l => (
            <button
              key={l.code}
              className={`lang-option ${l.code === lang ? 'active' : ''}`}
              onClick={() => { setLanguage(l.code); setOpen(false) }}
            >
              <span className="lang-flag">{l.flag}</span>
              <span>{l.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
