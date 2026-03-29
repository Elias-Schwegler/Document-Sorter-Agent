import { CheckCircle, AlertCircle, Info, X } from 'lucide-react'
import './Toast.css'

const icons = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
}

export default function Toast({ toasts, onRemove }) {
  if (!toasts || toasts.length === 0) return null

  return (
    <div className="toast-container">
      {toasts.map((toast) => {
        const Icon = icons[toast.type] || icons.info
        return (
          <div key={toast.id} className={`toast toast-${toast.type || 'info'}`}>
            <Icon size={18} className="toast-icon" />
            <span className="toast-message">{toast.message}</span>
            <button className="toast-close" onClick={() => onRemove(toast.id)}>
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
