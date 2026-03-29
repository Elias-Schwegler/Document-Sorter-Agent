import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useState, useCallback, createContext } from 'react'
import { I18nProvider } from './i18n'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'
import DocumentsPage from './pages/DocumentsPage'
import TelegramPage from './pages/TelegramPage'
import SettingsPage from './pages/SettingsPage'
import Toast from './components/Toast'

export const ToastContext = createContext(null)

export default function App() {
  const [toasts, setToasts] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [docCount, setDocCount] = useState(0)

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 5000)
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <I18nProvider>
    <ToastContext.Provider value={{ addToast }}>
      <BrowserRouter>
        <div className="app-layout">
          <Sidebar
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen(prev => !prev)}
            docCount={docCount}
          />
          <main className={`main-content ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
            <Routes>
              <Route path="/" element={<ChatPage />} />
              <Route path="/documents" element={<DocumentsPage onDocCountChange={setDocCount} />} />
              <Route path="/telegram" element={<TelegramPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
          <Toast toasts={toasts} onRemove={removeToast} />
        </div>
      </BrowserRouter>
    </ToastContext.Provider>
    </I18nProvider>
  )
}
