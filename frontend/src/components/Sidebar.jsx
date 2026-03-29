import { NavLink } from 'react-router-dom'
import { MessageSquare, FileText, Send, Settings, Menu, X } from 'lucide-react'
import { useI18n } from '../i18n'
import './Sidebar.css'

export default function Sidebar({ isOpen, onToggle, docCount }) {
  const { t } = useI18n()

  const navItems = [
    { to: '/', icon: MessageSquare, labelKey: 'nav.chat' },
    { to: '/documents', icon: FileText, labelKey: 'nav.documents' },
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
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-version">v1.0.0</div>
        </div>
      </aside>

      {isOpen && <div className="sidebar-overlay" onClick={onToggle} />}
    </>
  )
}
