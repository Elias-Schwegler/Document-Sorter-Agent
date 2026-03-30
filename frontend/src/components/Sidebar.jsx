import { useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { MessageSquare, FileText, Pencil, Send, Settings, Menu, X, Cpu } from 'lucide-react'
import { useI18n } from '../i18n'
import { documents as docsApi } from '../api'
import './Sidebar.css'

export default function Sidebar({ isOpen, onToggle, docCount, renameCount }) {
  const { t } = useI18n()
  const [pendingCount, setPendingCount] = useState(0)

  const pollPending = useCallback(async () => {
    try {
      const res = await docsApi.pending()
      setPendingCount(res.total || 0)
    } catch {}
  }, [])

  useEffect(() => {
    pollPending()
    const interval = setInterval(pollPending, 10000)
    return () => clearInterval(interval)
  }, [pollPending])

  const navItems = [
    { to: '/', icon: MessageSquare, labelKey: 'nav.chat' },
    { to: '/documents', icon: FileText, labelKey: 'nav.documents' },
    { to: '/rename', icon: Pencil, labelKey: 'nav.rename' },
    { to: '/telegram', icon: Send, labelKey: 'nav.telegram' },
    { to: '/settings', icon: Settings, labelKey: 'nav.settings' },
  ]

  return (
    <>
      <button className="sidebar-toggle-mobile" onClick={onToggle}>
        {isOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      <aside className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <FileText size={24} className="sidebar-logo-icon" />
            <span className="sidebar-title">DocManager</span>
          </div>
          <button className="sidebar-close btn-icon" onClick={onToggle}>
            <X size={18} />
          </button>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(({ to, icon: Icon, labelKey }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? 'active' : ''}`
              }
              end={to === '/'}
            >
              <Icon size={20} />
              <span>{t(labelKey)}</span>
              {labelKey === 'nav.documents' && docCount > 0 && (
                <span className="sidebar-badge">{docCount}</span>
              )}
              {labelKey === 'nav.rename' && renameCount > 0 && (
                <span className="sidebar-badge">{renameCount}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          {pendingCount > 0 && (
            <div className="sidebar-processing">
              <Cpu size={14} className="sidebar-processing-icon" />
              <span>Processing {pendingCount} doc{pendingCount !== 1 ? 's' : ''}...</span>
            </div>
          )}
          <div className="sidebar-version">v1.0.0</div>
        </div>
      </aside>

      {isOpen && <div className="sidebar-overlay" onClick={onToggle} />}
    </>
  )
}
