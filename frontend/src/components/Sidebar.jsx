import { NavLink } from 'react-router-dom'
import { MessageSquare, FileText, Send, Settings, Menu, X } from 'lucide-react'
import './Sidebar.css'

const navItems = [
  { to: '/', icon: MessageSquare, label: 'Chat' },
  { to: '/documents', icon: FileText, label: 'Documents' },
  { to: '/telegram', icon: Send, label: 'Telegram' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar({ isOpen, onToggle, docCount }) {
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
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? 'active' : ''}`
              }
              end={to === '/'}
            >
              <Icon size={20} />
              <span>{label}</span>
              {label === 'Documents' && docCount > 0 && (
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
