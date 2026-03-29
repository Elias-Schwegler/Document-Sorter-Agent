import { useState, useEffect, useContext } from 'react'
import { Send, Phone, Shield, Download, CheckSquare, Square, Loader, CheckCircle } from 'lucide-react'
import { telegram } from '../api'
import { ToastContext } from '../App'
import './TelegramPage.css'

export default function TelegramPage() {
  const [step, setStep] = useState(1)
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [status, setStatus] = useState(null)
  const [messages, setMessages] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importDone, setImportDone] = useState(false)
  const { addToast } = useContext(ToastContext)

  useEffect(() => {
    checkStatus()
  }, [])

  const checkStatus = async () => {
    try {
      const res = await telegram.getStatus()
      setStatus(res)
      if (res.authenticated) {
        setStep(3)
      }
    } catch {
      // Telegram not configured
    }
  }

  const handleStartAuth = async (e) => {
    e.preventDefault()
    if (!phone.trim()) return
    setLoading(true)
    try {
      await telegram.startAuth(phone.trim())
      setStep(2)
      addToast('Verification code sent', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async (e) => {
    e.preventDefault()
    if (!code.trim()) return
    setLoading(true)
    try {
      await telegram.verifyAuth(code.trim())
      setStep(3)
      addToast('Authenticated successfully', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleFetch = async () => {
    setLoading(true)
    try {
      const res = await telegram.fetchMessages()
      setMessages(res.messages || res || [])
      setSelected(new Set())
      addToast(`Found ${(res.messages || res || []).length} messages`, 'info')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selected.size === messages.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(messages.map(m => m.id)))
    }
  }

  const handleImport = async () => {
    if (selected.size === 0) return
    setImporting(true)
    try {
      await telegram.importMessages(Array.from(selected))
      setImportDone(true)
      addToast(`Imported ${selected.size} message(s)`, 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="telegram-page page">
      <div className="section-header">
        <h1 className="section-title">Telegram Import</h1>
      </div>

      <div className="telegram-steps">
        <div className={`telegram-step-indicator ${step >= 1 ? 'active' : ''} ${step > 1 ? 'done' : ''}`}>
          <div className="step-circle">{step > 1 ? <CheckCircle size={16} /> : '1'}</div>
          <span>Phone</span>
        </div>
        <div className="step-line" />
        <div className={`telegram-step-indicator ${step >= 2 ? 'active' : ''} ${step > 2 ? 'done' : ''}`}>
          <div className="step-circle">{step > 2 ? <CheckCircle size={16} /> : '2'}</div>
          <span>Verify</span>
        </div>
        <div className="step-line" />
        <div className={`telegram-step-indicator ${step >= 3 ? 'active' : ''} ${step > 3 ? 'done' : ''}`}>
          <div className="step-circle">{step > 3 ? <CheckCircle size={16} /> : '3'}</div>
          <span>Fetch</span>
        </div>
        <div className="step-line" />
        <div className={`telegram-step-indicator ${step >= 4 ? 'active' : ''} ${importDone ? 'done' : ''}`}>
          <div className="step-circle">{importDone ? <CheckCircle size={16} /> : '4'}</div>
          <span>Import</span>
        </div>
      </div>

      <div className="telegram-content card">
        {step === 1 && (
          <form className="telegram-form" onSubmit={handleStartAuth}>
            <div className="telegram-form-icon">
              <Phone size={32} />
            </div>
            <h2>Enter your phone number</h2>
            <p>We will send a verification code via Telegram.</p>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1234567890"
              disabled={loading}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!phone.trim() || loading}
            >
              {loading ? <Loader size={16} className="spinning" /> : <Send size={16} />}
              Send Code
            </button>
          </form>
        )}

        {step === 2 && (
          <form className="telegram-form" onSubmit={handleVerify}>
            <div className="telegram-form-icon">
              <Shield size={32} />
            </div>
            <h2>Enter verification code</h2>
            <p>Check your Telegram app for the code.</p>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="12345"
              disabled={loading}
              autoFocus
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!code.trim() || loading}
            >
              {loading ? <Loader size={16} className="spinning" /> : <Shield size={16} />}
              Verify
            </button>
          </form>
        )}

        {step === 3 && !messages.length && (
          <div className="telegram-fetch">
            <div className="telegram-form-icon">
              <Download size={32} />
            </div>
            <h2>Fetch Messages</h2>
            <p>Retrieve recent saved messages and documents from Telegram.</p>
            <button
              className="btn btn-primary"
              onClick={() => { handleFetch(); setStep(3) }}
              disabled={loading}
            >
              {loading ? <Loader size={16} className="spinning" /> : <Download size={16} />}
              Fetch Messages
            </button>
          </div>
        )}

        {step >= 3 && messages.length > 0 && !importDone && (
          <div className="telegram-messages">
            <div className="telegram-messages-header">
              <button className="btn btn-ghost btn-sm" onClick={toggleAll}>
                {selected.size === messages.length
                  ? <CheckSquare size={16} />
                  : <Square size={16} />}
                {selected.size === messages.length ? 'Deselect All' : 'Select All'}
              </button>
              <span className="telegram-selected-count">
                {selected.size} of {messages.length} selected
              </span>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => { handleImport(); setStep(4) }}
                disabled={selected.size === 0 || importing}
              >
                {importing ? <Loader size={14} className="spinning" /> : <Download size={14} />}
                Import Selected
              </button>
            </div>

            <div className="telegram-messages-list">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`telegram-msg ${selected.has(msg.id) ? 'selected' : ''}`}
                  onClick={() => toggleSelect(msg.id)}
                >
                  <div className="telegram-msg-check">
                    {selected.has(msg.id) ? <CheckSquare size={18} /> : <Square size={18} />}
                  </div>
                  <div className="telegram-msg-content">
                    <span className="telegram-msg-text">
                      {msg.text || msg.filename || 'Document'}
                    </span>
                    {msg.date && (
                      <span className="telegram-msg-date">
                        {new Date(msg.date).toLocaleString()}
                      </span>
                    )}
                  </div>
                  {msg.file_type && (
                    <span className="badge">{msg.file_type}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {importDone && (
          <div className="telegram-done">
            <CheckCircle size={48} className="telegram-done-icon" />
            <h2>Import Complete</h2>
            <p>{selected.size} message(s) have been imported to your document library.</p>
            <button
              className="btn btn-secondary"
              onClick={() => {
                setImportDone(false)
                setMessages([])
                setSelected(new Set())
                setStep(3)
              }}
            >
              Import More
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
